from __future__ import annotations
import abc
import asyncio
import json
import logging
from typing import Any, Dict, Generic, Optional, TypeVar, Set
import websockets
from websockets import WebSocketServerProtocol, WebSocketServer

T = TypeVar("T")
logger = logging.getLogger(__name__)


class BaseWebSocketServer(Generic[T], abc.ABC):
    """
    Abstract base WebSocket server using `websockets`.

    Subclass and implement:
      - on_connect(client)
      - on_message(client, message)
      - on_disconnect(client, code, reason)
      - on_error(client, exception)

    Features:
      - handles multiple clients
      - optional JSON encoding/decoding
      - broadcast helper
      - graceful shutdown
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        *,
        json_mode: bool = True,
        ping_interval: float = 20.0,
        ping_timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.json_mode = json_mode
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self._server: Optional[WebSocketServer] = None
        self._clients: Set[WebSocketServerProtocol] = set()
        self._stop_event = asyncio.Event()

    # ------------------------
    # Public API
    # ------------------------
    async def start(self) -> None:
        """Start the WebSocket server and accept incoming connections."""
        self._stop_event.clear()
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        self._server = await websockets.serve(
            self._handler,
            self.host,
            self.port,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
        )
        await self._stop_event.wait()

    async def stop(self) -> None:
        """Stop the server gracefully."""
        logger.info("Stopping WebSocket server...")
        self._stop_event.set()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for client in set(self._clients):
            await client.close(code=1001, reason="Server shutdown")
        self._clients.clear()

    async def broadcast(self, message: T) -> None:
        """Send a message to all connected clients."""
        if not self._clients:
            return
        payload = self._encode(message)
        await asyncio.gather(*(client.send(payload) for client in self._clients))

    # ------------------------
    # Internal connection handling
    # ------------------------
    async def _handler(self, websocket: WebSocketServerProtocol) -> None:
        client = websocket
        self._clients.add(client)
        try:
            await self._on_connect_safe(client)
            async for raw in websocket:
                try:
                    msg = self._decode(raw)
                    await self._on_message_safe(client, msg)
                except Exception as e:
                    await self._on_error_safe(client, e)
        except websockets.ConnectionClosed as cc:
            await self._on_disconnect_safe(client, cc.code, cc.reason)
        except Exception as e:
            await self._on_error_safe(client, e)
        finally:
            self._clients.discard(client)

    def _encode(self, message: T) -> str:
        return json.dumps(message) if self.json_mode else message  # type: ignore

    def _decode(self, raw: Any) -> T:
        if self.json_mode:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            return json.loads(raw)  # type: ignore
        return raw  # type: ignore

    # ------------------------
    # Safe dispatch wrappers
    # ------------------------
    async def _on_connect_safe(self, client: WebSocketServerProtocol) -> None:
        try:
            await self.on_connect(client)
        except Exception as e:
            await self._on_error_safe(client, e)

    async def _on_message_safe(self, client: WebSocketServerProtocol, message: T) -> None:
        try:
            await self.on_message(client, message)
        except Exception as e:
            await self._on_error_safe(client, e)

    async def _on_disconnect_safe(self, client: WebSocketServerProtocol, code: int, reason: str) -> None:
        try:
            await self.on_disconnect(client, code, reason)
        except Exception as e:
            await self._on_error_safe(client, e)

    async def _on_error_safe(self, client: WebSocketServerProtocol, exc: Exception) -> None:
        try:
            await self.on_error(client, exc)
        except Exception:
            logger.exception("Error in on_error handler")

    # ------------------------
    # Abstract methods
    # ------------------------
    @abc.abstractmethod
    async def on_connect(self, client: WebSocketServerProtocol) -> None:
        """Called when a client connects."""
        ...

    @abc.abstractmethod
    async def on_message(self, client: WebSocketServerProtocol, message: T) -> None:
        """Called when a message is received."""
        ...

    @abc.abstractmethod
    async def on_disconnect(self, client: WebSocketServerProtocol, code: int, reason: str) -> None:
        """Called when a client disconnects."""
        ...

    @abc.abstractmethod
    async def on_error(self, client: WebSocketServerProtocol, exc: Exception) -> None:
        """Called when an error occurs."""
        ...

# ------------------------
# Example
# ------------------------
# import asyncio
# from typing import Any
#
# class EchoServer(BaseWebSocketServer[Any]):
#     async def on_connect(self, client):
#         print(f"[+] Client connected: {client.remote_address}")
#         await client.send("Welcome to EchoServer!")
#
#     async def on_message(self, client, message):
#         print(f"[MSG] {client.remote_address} -> {message}")
#         await client.send(f"Echo: {message}")
#
#     async def on_disconnect(self, client, code, reason):
#         print(f"[-] Client disconnected ({code}): {reason}")
#
#     async def on_error(self, client, exc):
#         print(f"[ERR] {client.remote_address}: {exc}")
#
# async def main():
#     server = EchoServer(host="127.0.0.1", port=9001)
#     await server.start()
#
# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         print("Server stopped manually.")
#     except Exception as e:
#         print(f"Error: {e}")