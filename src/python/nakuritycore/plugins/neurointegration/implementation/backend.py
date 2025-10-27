# neuro_backend.py
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Optional, Callable, List, Tuple
import websockets
from websockets.server import WebSocketServerProtocol
import orjson

import neuro_api.command as command  # CoolCat command helpers

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProtocolError(Exception):
    pass


class NeuroBackendServer:
    """
    Minimal Neuro-compatible backend server that speaks the SDK wire-format:
      {"command": "...", "game": "...", "data": {...}}

    Hooks to override:
      - on_startup(game, ws)
      - on_context(game, message, silent, ws)
      - on_actions_register(game, actions, ws)
      - on_actions_unregister(game, action_names, ws)
      - on_action_result(game, id_, success, message, ws)
      - on_force_action(game, state, query, action_names, ephemeral_context, ws)
      - on_shutdown_graceful(game, wants_shutdown, ws)
      - on_shutdown_immediate(game, ws)
      - on_action_to_client(game, id_, name, data)  # invoked when server should push an "action" to client(s)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        # map: client -> (websocket, last_seen_game_name or None)
        self._clients: Dict[str, WebSocketServerProtocol] = {}
        # per-game registry: game_name -> dict[action_name -> action_meta]
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
    # Server -> client utilities (use SDK helpers)
    # ----------------
    async def send_action_to_client(self, ws: WebSocketServerProtocol, id_: str, name: str, data: Optional[str] = None):
        """Server -> Client: ask client to execute a registered action."""
        blob = command.action_command(id_, name, data)
        await self._safe_send(ws, blob)

    async def send_reregister_all(self, ws: WebSocketServerProtocol):
        blob = command.reregister_all_command()
        await self._safe_send(ws, blob)

    async def send_shutdown_graceful(self, ws: WebSocketServerProtocol, wants_shutdown: bool):
        blob = command.shutdown_graceful_command(wants_shutdown)
        await self._safe_send(ws, blob)

    async def send_shutdown_immediate(self, ws: WebSocketServerProtocol):
        blob = command.shutdown_immediate_command()
        await self._safe_send(ws, blob)

    # ----------------
    # Incoming command handlers
    # ----------------
    async def _handle_startup(self, game: str, data: Optional[Dict[str, Any]], ws: WebSocketServerProtocol):
        # startup clears stored registered actions for the game (per spec)
        self._game_actions[game] = {}
        await self.on_startup(game, ws)

    async def _handle_context(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        message = data.get("message")
        silent = bool(data.get("silent", True))
        await self.on_context(game, message, silent, ws)

    async def _handle_actions_register(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        actions = data.get("actions", [])
        # each action should be a dict matching Action._asdict() shape per SDK
        registered: List[Dict[str, Any]] = []
        for act in actions:
            name = act["name"]
            # store description and schema for server-side validation/knowledge
            self._game_actions.setdefault(game, {})[name] = {
                "description": act.get("description", ""),
                "schema": act.get("schema", None),
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
        state = data.get("state")
        query = data.get("query")
        action_names = data.get("action_names", [])
        ephemeral = bool(data.get("ephemeral_context", False))
        await self.on_force_action(game, state, query, action_names, ephemeral, ws)

    async def _handle_action_result(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        id_ = data["id"]
        success = bool(data["success"])
        message = data.get("message")
        await self.on_action_result(game, id_, success, message, ws)

    async def _handle_shutdown_ready(self, game: str, data: Optional[Dict[str, Any]], ws: WebSocketServerProtocol):
        # client telling server it's shutdown-ready — default behavior: log
        logger.info("Game %s reported shutdown-ready", game)

    async def _handle_shutdown_graceful_resp(self, game: str, data: Dict[str, Any], ws: WebSocketServerProtocol):
        wants = bool(data.get("wants_shutdown", False))
        await self.on_shutdown_graceful(game, wants, ws)

    # ----------------
    # Dispatch & websocket loop
    # ----------------
    async def _dispatch(self, payload: Dict[str, Any], ws: WebSocketServerProtocol):
        cmd = payload.get("command")
        game = payload.get("game")
        data = payload.get("data", {}) or {}

        if not isinstance(cmd, str):
            raise ProtocolError("missing or invalid 'command'")

        # route by command string - SDK-defined names are used here (see command.py)
        if cmd == "startup":
            if not isinstance(game, str):
                raise ProtocolError("startup requires 'game' string")
            await self._handle_startup(game, data, ws)
        elif cmd == "context":
            if not isinstance(game, str):
                raise ProtocolError("context requires 'game'")
            await self._handle_context(game, data, ws)
        elif cmd == "actions/register":
            if not isinstance(game, str):
                raise ProtocolError("actions/register requires 'game'")
            await self._handle_actions_register(game, data, ws)
        elif cmd == "actions/unregister":
            if not isinstance(game, str):
                raise ProtocolError("actions/unregister requires 'game'")
            await self._handle_actions_unregister(game, data, ws)
        elif cmd == "actions/force":
            if not isinstance(game, str):
                raise ProtocolError("actions/force requires 'game'")
            await self._handle_actions_force(game, data, ws)
        elif cmd == "action/result":
            if not isinstance(game, str):
                raise ProtocolError("action/result requires 'game'")
            await self._handle_action_result(game, data, ws)
        elif cmd == "shutdown/ready":
            if not isinstance(game, str):
                raise ProtocolError("shutdown/ready requires 'game'")
            await self._handle_shutdown_ready(game, data, ws)
        elif cmd == "shutdown/graceful":
            await self._handle_shutdown_graceful_resp(game, data, ws)
        else:
            logger.warning("Unknown command from client: %s", cmd)
            # per spec you may ignore unknown commands or respond with an error
            # here we simply log

    async def _ws_handler(self, ws: WebSocketServerProtocol, path: str):
        client_id = f"{ws.remote_address}"
        logger.info("Client connected: %s", client_id)
        self._clients[client_id] = ws
        try:
            async for raw in ws:
                try:
                    if isinstance(raw, str):
                        raw_bytes = raw.encode()
                    else:
                        raw_bytes = raw
                    payload = self._decode_message(raw_bytes)
                except ProtocolError as exc:
                    logger.exception("Protocol error: %s", exc)
                    # optionally send a simple error event (not SDK-defined): skip
                    continue
                try:
                    await self._dispatch(payload, ws)
                except ProtocolError as exc:
                    logger.exception("Dispatch protocol error: %s", exc)
                    continue
        except websockets.ConnectionClosedOK:
            logger.info("Client closed connection normally: %s", client_id)
        except Exception:
            logger.exception("Connection error")
        finally:
            self._clients.pop(client_id, None)
            logger.info("Client disconnected: %s", client_id)

    async def start(self):
        logger.info("Starting NeuroBackendServer on %s:%s", self.host, self.port)
        async with websockets.serve(self._ws_handler, self.host, self.port):
            await asyncio.Future()  # run forever

    # ----------------
    # Hook stubs - override these in a subclass or attach as callbacks
    # ----------------
    async def on_startup(self, game: str, ws: WebSocketServerProtocol):
        logger.info("on_startup %s", game)

    async def on_context(self, game: str, message: str, silent: bool, ws: WebSocketServerProtocol):
        logger.info("on_context %s | %s | silent=%s", game, message, silent)

    async def on_actions_register(self, game: str, actions: List[Dict[str, Any]], ws: WebSocketServerProtocol):
        logger.info("on_actions_register %s: %s", game, [a["name"] for a in actions])

    async def on_actions_unregister(self, game: str, action_names: List[str], ws: WebSocketServerProtocol):
        logger.info("on_actions_unregister %s: %s", game, action_names)

    async def on_force_action(self, game: str, state: str, query: str, action_names: List[str], ephemeral: bool, ws: WebSocketServerProtocol):
        logger.info("on_force_action %s: %s", game, action_names)
        # Default behavior: if any connected client for that game exists, push the first action as an example
        # (apps should implement proper selection/dispatch)
        # Find a client for this game
        for client_ws in list(self._clients.values()):
            try:
                await self.send_action_to_client(client_ws, "forced-1", action_names[0], None)
                break
            except Exception:
                continue

    async def on_action_result(self, game: str, id_: str, success: bool, message: Optional[str], ws: WebSocketServerProtocol):
        logger.info("on_action_result %s: id=%s success=%s message=%s", game, id_, success, message)

    async def on_shutdown_graceful(self, game: str, wants_shutdown: bool, ws: WebSocketServerProtocol):
        logger.info("on_shutdown_graceful %s wants=%s", game, wants_shutdown)

    async def on_shutdown_immediate(self, game: str, ws: WebSocketServerProtocol):
        logger.info("on_shutdown_immediate %s", game)

