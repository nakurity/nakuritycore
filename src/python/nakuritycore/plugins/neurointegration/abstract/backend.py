# neuro_backend.py
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Optional, List
import websockets
from websockets.server import WebSocketServerProtocol
import orjson
from abc import ABC, abstractmethod

import neuro_api.command as command  # external CoolCat-style helpers

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProtocolError(Exception):
    """Raised for invalid or malformed protocol messages."""
    pass


class AbstractNeuroBackend(ABC):
    """
    Abstract Neuro-compatible backend that speaks the Neuro SDK wire-format:
      {"command": "...", "game": "...", "data": {...}}

    Subclasses implement hooks like:
      - on_startup(game, ws)
      - on_context(game, message, silent, ws)
      - on_actions_register(game, actions, ws)
      - on_actions_unregister(game, action_names, ws)
      - on_action_result(game, id_, success, message, ws)
      - on_force_action(game, state, query, action_names, ephemeral_context, ws)
      - on_shutdown_graceful(game, wants_shutdown, ws)
      - on_shutdown_immediate(game, ws)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._clients: Dict[str, WebSocketServerProtocol] = {}
        self._game_actions: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._server: Optional[asyncio.AbstractServer] = None

    # ----------------
    # Internal helpers
    # ----------------
    @staticmethod
    def _decode_message(raw: bytes) -> Dict[str, Any]:
        try:
            payload = orjson.loads(raw)
            if not isinstance(payload, dict):
                raise ProtocolError("payload must be an object")
            return payload
        except Exception as exc:
            raise ProtocolError(f"invalid JSON: {exc}") from exc

    async def _safe_send(self, ws: WebSocketServerProtocol, blob: bytes) -> None:
        try:
            await ws.send(blob)
        except Exception:
            logger.exception("Failed to send to client %s", getattr(ws, "remote_address", None))

    # ----------------
    # Server -> client utilities
    # ----------------
    async def send_action_to_client(
        self, ws: WebSocketServerProtocol, id_: str, name: str, data: Optional[str] = None
    ):
        """Server -> Client: ask client to execute a registered action."""
        blob = command.action_command(id_, name, data)
        await self._safe_send(ws, blob)

    async def send_reregister_all(self, ws: WebSocketServerProtocol):
        await self._safe_send(ws, command.reregister_all_command())

    async def send_shutdown_graceful(self, ws: WebSocketServerProtocol, wants_shutdown: bool):
        await self._safe_send(ws, command.shutdown_graceful_command(wants_shutdown))

    async def send_shutdown_immediate(self, ws: WebSocketServerProtocol):
        await self._safe_send(ws, command.shutdown_immediate_command())

    # ----------------
    # Command Dispatch
    # ----------------
    async def _dispatch(self, payload: Dict[str, Any], ws: WebSocketServerProtocol):
        cmd = payload.get("command")
        game = payload.get("game")
        data = payload.get("data", {}) or {}

        if not isinstance(cmd, str):
            raise ProtocolError("missing or invalid 'command'")

        handler_map = {
            "startup": self._handle_startup,
            "context": self._handle_context,
            "actions/register": self._handle_actions_register,
            "actions/unregister": self._handle_actions_unregister,
            "actions/force": self._handle_actions_force,
            "action/result": self._handle_action_result,
            "shutdown/ready": self._handle_shutdown_ready,
            "shutdown/graceful": self._handle_shutdown_graceful_resp,
        }

        handler = handler_map.get(cmd)
        if handler is None:
            logger.warning("Unknown command from client: %s", cmd)
            return

        await handler(game, data, ws)

    # ----------------
    # Handlers (internal routing)
    # ----------------
    async def _handle_startup(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        self._game_actions[game] = {}
        await self.on_startup(game, ws)

    async def _handle_context(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        await self.on_context(game, data.get("message"), bool(data.get("silent", True)), ws)

    async def _handle_actions_register(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        actions = data.get("actions", [])
        registered = []
        for act in actions:
            name = act["name"]
            self._game_actions.setdefault(game, {})[name] = {
                "description": act.get("description", ""),
                "schema": act.get("schema"),
            }
            registered.append(act)
        await self.on_actions_register(game, registered, ws)

    async def _handle_actions_unregister(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        action_names = data.get("action_names", [])
        for n in action_names:
            if game in self._game_actions:
                self._game_actions[game].pop(n, None)
        await self.on_actions_unregister(game, action_names, ws)

    async def _handle_actions_force(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        await self.on_force_action(
            game,
            data.get("state"),
            data.get("query"),
            data.get("action_names", []),
            bool(data.get("ephemeral_context", False)),
            ws,
        )

    async def _handle_action_result(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        await self.on_action_result(
            game,
            data["id"],
            bool(data.get("success")),
            data.get("message"),
            ws,
        )

    async def _handle_shutdown_ready(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        logger.info("Game %s reported shutdown-ready", game)

    async def _handle_shutdown_graceful_resp(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        await self.on_shutdown_graceful(game, bool(data.get("wants_shutdown", False)), ws)

    # ----------------
    # WebSocket Lifecycle
    # ----------------
    async def _ws_handler(self, ws: WebSocketServerProtocol, path: str):
        client_id = f"{ws.remote_address}"
        logger.info("Client connected: %s", client_id)
        self._clients[client_id] = ws
        try:
            async for raw in ws:
                try:
                    raw_bytes = raw.encode() if isinstance(raw, str) else raw
                    payload = self._decode_message(raw_bytes)
                    await self._dispatch(payload, ws)
                except ProtocolError as exc:
                    logger.warning("Protocol error: %s", exc)
        except websockets.ConnectionClosedOK:
            logger.info("Client closed connection normally: %s", client_id)
        except Exception:
            logger.exception("Connection error")
        finally:
            self._clients.pop(client_id, None)
            logger.info("Client disconnected: %s", client_id)

    async def start(self):
        logger.info("Starting NeuroBackend on %s:%s", self.host, self.port)
        async with websockets.serve(self._ws_handler, self.host, self.port):
            await asyncio.Future()

    # ----------------
    # Abstract Hooks
    # ----------------
    @abstractmethod
    async def on_startup(self, game: str, ws: WebSocketServerProtocol): ...

    @abstractmethod
    async def on_context(self, game: str, message: str, silent: bool, ws: WebSocketServerProtocol): ...

    @abstractmethod
    async def on_actions_register(self, game: str, actions: List[Dict[str, Any]], ws: WebSocketServerProtocol): ...

    @abstractmethod
    async def on_actions_unregister(self, game: str, action_names: List[str], ws: WebSocketServerProtocol): ...

    @abstractmethod
    async def on_force_action(
        self, game: str, state: str, query: str, action_names: List[str], ephemeral: bool, ws: WebSocketServerProtocol
    ): ...

    @abstractmethod
    async def on_action_result(
        self, game: str, id_: str, success: bool, message: Optional[str], ws: WebSocketServerProtocol
    ): ...

    @abstractmethod
    async def on_shutdown_graceful(self, game: str, wants_shutdown: bool, ws: WebSocketServerProtocol): ...

    @abstractmethod
    async def on_shutdown_immediate(self, game: str, ws: WebSocketServerProtocol): ...

    @abstractmethod
    async def on_shutdown_ready(self, game: str, ws: WebSocketServerProtocol): ...