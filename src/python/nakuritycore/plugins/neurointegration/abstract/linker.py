# neuro_integration_plugin.py
from __future__ import annotations

import abc
import asyncio
import logging
import uuid
from typing import (
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

logger = logging.getLogger(__name__)


class AbstractIntegration(abc.ABC):
    """
    Minimal expected interface for a Neuro integration.
    Implementations should connect to a backend (server/client) and
    handle Neuro command messages (see neuro_api.* for command types).
    """

    @abc.abstractmethod
    async def read_message(self) -> Tuple[str, Optional[str], Optional[dict]]:
        """Read a single message: (command_type, game_title, data)."""
        ...

    @abc.abstractmethod
    async def send_command(
        self, command_type: str, game_title: Optional[str], data: Optional[dict]
    ) -> None:
        """Send a message."""
        ...

    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this integration."""
        ...


class AbstractNeuroIntegrationPlugin(abc.ABC):
    """
    Abstract plugin class that connects multiple Neuro integrations together.

    Responsibilities:
    - Maintain a registry of integrations.
    - Read from all integrations concurrently.
    - Forward or transform commands according to routing logic.
    - Keep action ID mappings (proxying action IDs between integrations).
    """

    def __init__(self, *, id_prefix: str = "multi", loop: Optional[asyncio.AbstractEventLoop] = None):
        self._integrations: Dict[str, AbstractIntegration] = {}
        self._tasks: Set[asyncio.Task] = set()
        self._stop = False
        self._loop = loop or asyncio.get_event_loop()
        self._id_prefix = id_prefix
        self._id_map: Dict[str, Tuple[str, str]] = {}  # proxied_id -> (origin, original_id)

    # === Registration ===

    def register_integration(self, integration: AbstractIntegration) -> None:
        """Register a new integration for linking."""
        name = integration.name()
        if name in self._integrations:
            raise ValueError(f"Integration '{name}' already registered")
        self._integrations[name] = integration
        logger.info("Registered integration: %s", name)

    def unregister_integration(self, name: str) -> None:
        """Unregister an integration."""
        if name in self._integrations:
            del self._integrations[name]
            logger.info("Unregistered integration: %s", name)

    # === Core lifecycle ===

    def start(self) -> None:
        """Start all integration reader loops."""
        for name, integ in self._integrations.items():
            task = self._loop.create_task(self._reader_loop(integ))
            self._tasks.add(task)
        logger.debug("NeuroIntegrationPlugin started with %d integrations", len(self._integrations))

    async def stop(self) -> None:
        """Stop all tasks."""
        self._stop = True
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.debug("NeuroIntegrationPlugin stopped")

    # === Abstract routing logic ===

    @abc.abstractmethod
    async def route_message(
        self,
        origin: str,
        command_type: str,
        game_title: Optional[str],
        data: Optional[dict],
    ) -> List[Tuple[str, str, Optional[dict]]]:
        """
        Decide how to route a given message.
        Should return a list of tuples:
            (destination_name, command_type, modified_data)
        The plugin will automatically send those commands to the destinations.
        """
        ...

    # === Reader loop ===

    async def _reader_loop(self, integration: AbstractIntegration) -> None:
        """Continuously read messages from an integration and route them."""
        origin = integration.name()
        try:
            while not self._stop:
                msg = await integration.read_message()
                if msg is None:
                    await asyncio.sleep(0.01)
                    continue

                command_type, game_title, data = msg

                try:
                    routes = await self.route_message(origin, command_type, game_title, data)
                    for dest_name, new_type, new_data in routes:
                        dest = self._integrations.get(dest_name)
                        if dest:
                            await dest.send_command(new_type, game_title, new_data)
                except Exception:
                    logger.exception("Error routing message from %s", origin)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Reader loop for %s crashed", origin)

    # === Utilities ===

    def proxy_action_id(self, origin: str, original_id: str) -> str:
        """Generate a proxied ID for cross-integration action mapping."""
        proxied = f"{self._id_prefix}-{uuid.uuid4().hex}"
        self._id_map[proxied] = (origin, original_id)
        return proxied

    def resolve_action_result(self, proxied_id: str) -> Optional[Tuple[str, str]]:
        """Return (origin_integration_name, original_id) for a proxied result."""
        return self._id_map.pop(proxied_id, None)

# ----------------------
# Example Implementation
# ----------------------
# class BroadcastPlugin(AbstractNeuroIntegrationPlugin):
#     """Simple example that broadcasts every message to all other integrations."""
#
#     async def route_message(self, origin, command_type, game_title, data):
#         routes = []
#         for dest_name in self._integrations.keys():
#             if dest_name == origin:
#                 continue
#             routes.append((dest_name, command_type, data))
#         return routes

# ----------------------
# Example Usage
# ----------------------
# async def main():
#     plugin = BroadcastPlugin()
#
#     # Register integrations (they must subclass AbstractIntegration)
#     plugin.register_integration(MyIntegrationA())
#     plugin.register_integration(MyIntegrationB())
#     plugin.register_integration(MyIntegrationC())
#
#     plugin.start()
#     await asyncio.sleep(3600)
#     await plugin.stop()