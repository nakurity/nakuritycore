from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Tuple

from ..abstract.linker import (
    AbstractNeuroIntegrationPlugin,
)

logger = logging.getLogger(__name__)


class NeuroIntegrationPlugin(AbstractNeuroIntegrationPlugin):
    """
    Concrete implementation of the abstract plugin:
    - Handles any number of integrations.
    - Forwards commands between them based on Neuro protocol types.
    - Maintains proxy IDs for `action` / `action/result` messages.
    - Automatically synchronizes action registration lists.
    """

    def __init__(self, *, id_prefix: str = "multi", loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(id_prefix=id_prefix, loop=loop)
        self._registered_actions: Dict[str, set[str]] = {}

    async def route_message(
        self,
        origin: str,
        command_type: str,
        game_title: Optional[str],
        data: Optional[dict],
    ) -> List[Tuple[str, str, Optional[dict]]]:
        """Implements Neuro command routing logic."""

        routes: List[Tuple[str, str, Optional[dict]]] = []
        ct = command_type or ""
        payload = data or {}

        # Initialize registry for origin if missing
        self._registered_actions.setdefault(origin, set())

        # === Core Routing Logic ===
        if ct in ("startup", "context"):
            # broadcast startup/context to all others
            for dest_name in self._integrations:
                if dest_name == origin:
                    continue
                routes.append((dest_name, ct, payload))
            return routes

        if ct == "actions/register":
            # update internal registry
            try:
                actions = [a["name"] for a in payload.get("actions", [])]
            except Exception:
                actions = []
            self._registered_actions[origin].update(actions)

            # forward registration to all other integrations
            for dest_name in self._integrations:
                if dest_name == origin:
                    continue
                routes.append((dest_name, ct, payload))
            return routes

        if ct == "actions/unregister":
            try:
                names = payload.get("action_names", [])
            except Exception:
                names = []
            for n in names:
                self._registered_actions[origin].discard(n)
            for dest_name in self._integrations:
                if dest_name != origin:
                    routes.append((dest_name, ct, payload))
            return routes

        if ct == "actions/force":
            # direct broadcast (force requests have no return)
            for dest_name in self._integrations:
                if dest_name != origin:
                    routes.append((dest_name, ct, payload))
            return routes

        if ct == "action":
            # incoming action request
            orig_id = payload.get("id")
            if not orig_id:
                return []
            proxied = self.proxy_action_id(origin, orig_id)

            proxied_payload = dict(payload)
            proxied_payload["id"] = proxied

            # find who registered this action name
            action_name = payload.get("name")
            targets = self._find_action_targets(origin, action_name)
            for dest_name in targets:
                routes.append((dest_name, ct, proxied_payload))
            return routes

        if ct == "action/result":
            result_id = payload.get("id")
            if not result_id:
                return []
            resolved = self.resolve_action_result(result_id)
            if not resolved:
                logger.warning("Received action/result with unmapped ID: %s", result_id)
                return []
            origin_name, original_id = resolved
            forward_payload = dict(payload)
            forward_payload["id"] = original_id
            routes.append((origin_name, ct, forward_payload))
            return routes

        # Default fallback: broadcast unknown command types
        for dest_name in self._integrations:
            if dest_name != origin:
                routes.append((dest_name, ct, payload))
        return routes

    # === Helpers ===

    def _find_action_targets(self, origin: str, action_name: Optional[str]) -> List[str]:
        """Find integrations that have registered the given action."""
        if not action_name:
            return []
        targets: List[str] = []
        for dest_name, actions in self._registered_actions.items():
            if dest_name != origin and action_name in actions:
                targets.append(dest_name)
        if not targets:
            logger.debug("No registered targets found for action '%s'", action_name)
        return targets
    
# ----------------------
# Example implementation
# ----------------------
#
# class DummyIntegration(AbstractIntegration):
#     def __init__(self, name: str):
#         self._name = name
#         self._inbox: asyncio.Queue = asyncio.Queue()
#
#     def name(self) -> str:
#         return self._name
#
#     async def read_message(self):
#         return await self._inbox.get()
#
#     async def send_command(self, command_type, game_title, data):
#         print(f"[{self._name} RECEIVED] {command_type} {game_title} {data}")
#
#     # helper for testing
#     async def simulate_incoming(self, command_type, game_title, data):
#         await self._inbox.put((command_type, game_title, data))

# ----------------------
# Example usage
# ----------------------
# 
# async def main():
#     a, b, c = DummyIntegration("A"), DummyIntegration("B"), DummyIntegration("C")
#     plugin = NeuroIntegrationPlugin()
#     plugin.register_integration(a)
#     plugin.register_integration(b)
#     plugin.register_integration(c)
#     plugin.start()
#
#     # simulate action registration and call
#     await a.simulate_incoming("actions/register", None, {"actions": [{"name": "greet"}]})
#     await b.simulate_incoming("action", None, {"id": "abc", "name": "greet", "data": {"msg": "Hello!"}})
#
#     await asyncio.sleep(0.5)
#     await plugin.stop()
#
# asyncio.run(main())