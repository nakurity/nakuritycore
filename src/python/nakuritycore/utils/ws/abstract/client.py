from __future__ import annotations
import abc
import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable, Dict, Generic, Optional, TypeVar
import websockets
from websockets import WebSocketClientProtocol

T = TypeVar("T")  # message payload type (e.g., dict for JSON, str for plain)

logger = logging.getLogger(__name__)


class BaseWebSocketClient(Generic[T], abc.ABC):
    """
    Generic abstract asyncio WebSocket client using `websockets`.
    Subclass and override hooks: on_open, on_message, on_close, on_error.

    Key features:
    - automatic reconnect with exponential backoff
    - outgoing queue (send())
    - optional json encode/decode (json_mode)
    - heartbeat/ping
    - graceful start/stop
    """

    def __init__(
        self,
        url: str,
        *,
        json_mode: bool = True,
        ping_interval: float = 20.0,
        ping_timeout: float = 10.0,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
        max_queue_size: int = 1000,
    ):
        self.url = url
        self.json_mode = json_mode
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay

        self._outgoing: asyncio.Queue[T] = asyncio.Queue(maxsize=max_queue_size)
        self._ws: Optional[WebSocketClientProtocol] = None
        self._main_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()

    # ------------------------
    # Public lifecycle methods
    # ------------------------
    def start(self) -> None:
        """Start background connect/read/send tasks. Not re-entrant."""
        if self._main_task and not self._main_task.done():
            raise RuntimeError("Client already started")
        self._stop_event.clear()
        loop = asyncio.get_event_loop()
        self._main_task = loop.create_task(self._run_loop())
        logger.debug("WebSocket client started")

    async def stop(self) -> None:
        """Gracefully stop the client and wait for tasks to complete."""
        self._stop_event.set()
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception as e:
                logger.exception("Error closing websocket: %s", e)
        if self._main_task:
            await asyncio.shield(self._main_task)
        logger.debug("WebSocket client stopped")

    async def wait_connected(self, timeout: Optional[float] = None) -> bool:
        """Wait until connection is established. Returns True if connected."""
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ------------------------
    # Sending
    # ------------------------
    async def send(self, message: T, *, block: bool = True) -> None:
        """Queue a message for sending. If block is False, raises queue.Full immediately."""
        if not block:
            self._outgoing.put_nowait(message)
        else:
            await self._outgoing.put(message)

    async def _send_loop(self) -> None:
        assert self._ws is not None
        while not self._stop_event.is_set() and self._ws.open:
            try:
                msg = await asyncio.wait_for(self._outgoing.get(), timeout=self.ping_interval)
            except asyncio.TimeoutError:
                # nothing to send, loop will continue (ping handled elsewhere)
                continue

            try:
                await self._send_raw(msg)
            except Exception as e:
                logger.exception("Send error: %s", e)
                await self._handle_error(e)
                # on send failure: requeue if still possible
                try:
                    self._outgoing.put_nowait(msg)
                except asyncio.QueueFull:
                    logger.warning("Outgoing queue full; dropped message")

    async def _send_raw(self, message: T) -> None:
        assert self._ws is not None
        if self.json_mode:
            payload = json.dumps(message)  # type: ignore[arg-type]
            await self._ws.send(payload)
        else:
            await self._ws.send(message)  # type: ignore[arg-type]

    # ------------------------
    # Receiving / connection
    # ------------------------
    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._iter_messages(self._ws):
                try:
                    msg = self._decode(raw)
                except Exception as e:
                    logger.exception("Failed to decode message: %s", e)
                    await self._handle_error(e)
                    continue
                await self._handle_message(msg)
        except websockets.ConnectionClosed as cc:
            logger.info("Connection closed: %s", cc)
            await self._handle_close(cc.code, cc.reason)
        except Exception as e:
            logger.exception("Receive loop exception: %s", e)
            await self._handle_error(e)

    async def _iter_messages(self, ws: WebSocketClientProtocol) -> AsyncIterator[Any]:
        # yields raw messages (str/bytes)
        while not self._stop_event.is_set() and ws.open:
            msg = await ws.recv()
            yield msg

    def _decode(self, raw: Any) -> T:
        if self.json_mode:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            return json.loads(raw)  # type: ignore[return-value]
        return raw  # type: ignore[return-value]

    # ------------------------
    # Connection loop + backoff
    # ------------------------
    async def _run_loop(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            backoff = min(self.reconnect_base_delay * (2 ** attempt), self.reconnect_max_delay)
            try:
                logger.info("Connecting to %s", self.url)
                async with websockets.connect(
                    self.url, ping_interval=None, ping_timeout=None
                ) as ws:
                    self._ws = ws
                    self._connected_event.set()
                    attempt = 0
                    logger.info("Connected to %s", self.url)
                    await self._handle_open()

                    # create tasks: recv, send, ping
                    tasks = [
                        asyncio.create_task(self._recv_loop(), name="ws-recv"),
                        asyncio.create_task(self._send_loop(), name="ws-send"),
                        asyncio.create_task(self._ping_loop(), name="ws-ping"),
                    ]
                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )

                    # cancel remaining tasks
                    for p in pending:
                        p.cancel()
                        with contextlib.suppress(Exception):
                            await p

                    # if any task raised, re-raise to outer except block
                    for d in done:
                        if d.exception():
                            raise d.exception()

            except asyncio.CancelledError:
                logger.debug("Run loop cancelled")
                break
            except Exception as exc:
                logger.exception("Connection attempt failed: %s", exc)
                await self._handle_error(exc)
                attempt += 1
                # wait with jitter
                jitter = min(backoff, 30.0) * 0.1
                delay = backoff + (jitter * (2 * (random.random() - 0.5)))
                logger.info("Reconnecting in %.1f seconds", delay)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    # stopped during backoff
                    break
                except asyncio.TimeoutError:
                    continue
            finally:
                self._connected_event.clear()
                self._ws = None

    # ------------------------
    # Ping / heartbeat
    # ------------------------
    async def _ping_loop(self) -> None:
        assert self._ws is not None
        while not self._stop_event.is_set() and self._ws.open:
            try:
                await asyncio.wait_for(self._ws.ping(), timeout=self.ping_timeout)
            except asyncio.TimeoutError:
                logger.warning("Ping timeout; closing connection")
                await self._ws.close()
                break
            except Exception as e:
                logger.exception("Ping error: %s", e)
                await self._handle_error(e)
                break
            await asyncio.sleep(self.ping_interval)

    # ------------------------
    # Hook dispatchers (wrap user overrides with try/except)
    # ------------------------
    async def _handle_open(self) -> None:
        try:
            await self.on_open()
        except Exception as e:
            logger.exception("on_open error: %s", e)
            await self._handle_error(e)

    async def _handle_message(self, msg: T) -> None:
        try:
            await self.on_message(msg)
        except Exception as e:
            logger.exception("on_message error: %s", e)
            await self._handle_error(e)

    async def _handle_close(self, code: int, reason: str) -> None:
        try:
            await self.on_close(code, reason)
        except Exception as e:
            logger.exception("on_close error: %s", e)
            await self._handle_error(e)

    async def _handle_error(self, exc: Exception) -> None:
        try:
            await self.on_error(exc)
        except Exception:
            logger.exception("on_error raised while handling another error")

    # ------------------------
    # Abstract hooks to override
    # ------------------------
    @abc.abstractmethod
    async def on_open(self) -> None:
        """Called when the websocket connection is opened."""
        ...

    @abc.abstractmethod
    async def on_message(self, message: T) -> None:
        """Called when a decoded message arrives."""
        ...

    @abc.abstractmethod
    async def on_close(self, code: int, reason: str) -> None:
        """Called when the socket closes (either graceful or not)."""
        ...

    @abc.abstractmethod
    async def on_error(self, exc: Exception) -> None:
        """Called on internal errors; implementers can log/record/alert."""
        ...

# ------------------------
# Example subclass + usage
# ------------------------
# import contextlib
# import random
#
# class EchoClient(BaseWebSocketClient[Dict[str, Any]]):
#     async def on_open(self) -> None:
#         logger.info("OPEN -> sending hello")
#         await self.send({"type": "hello", "payload": "hi"})
#
#     async def on_message(self, message: Dict[str, Any]) -> None:
#         logger.info("RECV -> %r", message)
#         # example: echo back
#         if message.get("type") == "ping":
#             await self.send({"type": "pong", "payload": None})
#
#     async def on_close(self, code: int, reason: str) -> None:
#         logger.info("CLOSE -> %s %s", code, reason)
#
#     async def on_error(self, exc: Exception) -> None:
#         logger.error("ERR -> %s", exc)
#
#
# # Run example (if running as a script)
# if __name__ == "__main__":
#     import sys
#     logging.basicConfig(level=logging.INFO)
#     ws_url = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8765"
#     client = EchoClient(ws_url, json_mode=True)
#
#     async def main():
#         client.start()
#         # wait to connect or exit after timeout
#         connected = await client.wait_connected(timeout=5.0)
#         if not connected:
#             logger.error("Failed to connect in 5s, exiting.")
#             await client.stop()
#             return
#         # simulate some work
#         await asyncio.sleep(60)
#         await client.stop()
#
#     asyncio.run(main())
