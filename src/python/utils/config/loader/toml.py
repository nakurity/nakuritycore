from pathlib import Path
from typing import Dict, Any
from ....data.config import BaseConfigLoader

import tomllib

class TomlConfigLoader(BaseConfigLoader):
    """Concrete TOML config loader (Python 3.11+)."""

    def load_file(self, path: Path) -> Dict[str, Any]:
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            if not isinstance(data, dict):
                raise ValueError("TOML root must be a table/dict")
            return data
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Failed to parse TOML config ({path}): {e}")

    def default_config(self) -> Dict[str, Any]:
        return {
            "debug": {"enabled": False, "logging": {"level": "INFO"}},
            "app": {"version": "0.1.0", "name": "MyApp"},
        }