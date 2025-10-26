import json
from pathlib import Path
from typing import Any, Dict, Optional
from ....data.config import BaseConfigLoader

# ==========================================
# Base JSON/YAML Config Loader Implementations
# ==========================================

class JsonConfigLoader(BaseConfigLoader):
    """Concrete JSON config loader with safe defaults."""

    def load_file(self, path: Path) -> Dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("JSON root must be an object/dict")
            return data
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON config ({path}): {e}")

    def default_config(self) -> Dict[str, Any]:
        return {
            "debug": {
                "enabled": False,
                "logging": {"level": "WARNING", "console": True},
            },
            "connection": {"timeout": 30},
        }
    

# ==========================================
# Shared Singleton Access / Loader Management
# ==========================================
    
_config_loader: Optional[BaseConfigLoader] = None


def get_config_loader(config_path: Optional[str] = None) -> BaseConfigLoader:
    global _config_loader
    if _config_loader is None or config_path is not None:
        _config_loader = JsonConfigLoader(config_path)
    return _config_loader