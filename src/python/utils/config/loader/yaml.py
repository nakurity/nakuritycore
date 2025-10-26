import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from ....data.config import BaseConfigLoader

class YamlConfigLoader(BaseConfigLoader):
    """Concrete YAML config loader with structured default values."""

    def load_file(self, path: Path) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("YAML root must be a mapping/dict")
            return data
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML config ({path}): {e}")

    def default_config(self) -> Dict[str, Any]:
        return {
            "debug": {
                "enabled": True,
                "trace": {"enabled": False, "verbose": False},
                "logging": {"level": "INFO", "console": True},
            },
            "connection": {
                "retry": {
                    "max_attempts": 10,
                    "initial_delay": 5,
                    "max_delay": 60,
                    "backoff_multiplier": 1.5,
                }
            },
        }

# ==========================================
# Shared singleton access
# ==========================================

_config_loader: Optional[BaseConfigLoader] = None


def get_config_loader(config_path: Optional[str] = None) -> BaseConfigLoader:
    global _config_loader
    if _config_loader is None or config_path is not None:
        _config_loader = YamlConfigLoader(config_path)
    return _config_loader