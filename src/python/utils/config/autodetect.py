from typing import Type
from pathlib import Path

from .loader import TomlConfigLoader, YamlConfigLoader, JsonConfigLoader
from ...data.config import BaseConfigLoader

def detect_loader_from_path(path: Path) -> Type[BaseConfigLoader]:
    ext = path.suffix.lower()
    if ext in {".yaml", ".yml"}:
        return YamlConfigLoader
    elif ext == ".json":
        return JsonConfigLoader
    elif ext == ".toml":
        return TomlConfigLoader
    else:
        raise ValueError(f"Unsupported config file type: {ext}")