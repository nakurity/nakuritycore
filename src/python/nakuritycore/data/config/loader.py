"""
Abstract configuration loader base class.
Other loaders (YAML, JSON, etc.) can subclass this for shared logic.
"""

import sys
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional


class BaseConfigLoader(ABC):
    """Abstract base class for all configuration loaders."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else self.default_config_path()
        self.config = self._load_config_safe()

    # ------------------------------
    # Abstracts — must implement
    # ------------------------------

    @abstractmethod
    def load_file(self, path: Path) -> Dict[str, Any]:
        """Parse and return the raw config from file."""
        pass

    @abstractmethod
    def default_config(self) -> Dict[str, Any]:
        """Return fallback configuration if file missing or broken."""
        pass

    # ------------------------------
    # Shared logic for all loaders
    # ------------------------------

    def default_config_path(self) -> Path:
        """Default location for config files."""
        return Path(__file__).parent.parent / "config.yaml"

    def _load_config_safe(self) -> Dict[str, Any]:
        """Wrapper for load_file() with error handling."""
        try:
            if not self.config_path.exists():
                print(f"[Config] File not found: {self.config_path}")
                return self.default_config()
            return self.load_file(self.config_path)
        except Exception as e:
            print(f"[Config] Failed to load {self.config_path}: {e}")
            return self.default_config()

    def get(self, *path: str, default: Any = None) -> Any:
        """Generic safe access via path keys."""
        node = self.config
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def merge(self, updates: Dict[str, Any]) -> None:
        """Merge in overrides recursively."""
        def deep_merge(base, new):
            for k, v in new.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
        deep_merge(self.config, updates)

    # ------------------------------
    # Optional extensions
    # ------------------------------

    def setup_logging(self) -> None:
        """Generic logging setup based on config['debug']['logging']."""
        log_config = self.get("debug", "logging", default={})
        level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        if log_config.get("file"):
            path = Path(log_config["file"])
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(path)
            handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            logging.getLogger().addHandler(handler)

    def apply_trace(self, trace_func) -> None:
        """Optionally attach a trace function based on config."""
        if not self.get("debug", "trace", "enabled", default=False):
            sys.settrace(None)
            return
        if hasattr(trace_func, "config"):
            trace_func.config.update(self.get("debug", "trace", default={}))
        sys.settrace(trace_func)
