from ...data.config import BaseConfigLoader
from typing import Optional, Type
from pathlib import Path
from .loader import YamlConfigLoader

_config_loader: Optional[BaseConfigLoader] = None


def get_config_loader(
    config_path: Optional[str | Path] = None,
    loader_cls: Optional[Type[BaseConfigLoader]] = None,
) -> BaseConfigLoader:
    """
    Get or create a shared configuration loader.

    Args:
        config_path: Optional path to the configuration file.
        loader_cls: Optional loader class (defaults to YAML if unspecified).

    Returns:
        A singleton instance of the selected config loader.
    """
    global _config_loader

    if loader_cls is None:
        loader_cls = YamlConfigLoader

    if _config_loader is None or config_path is not None:
        path = Path(config_path) if config_path else None
        _config_loader = loader_cls(path)

    return _config_loader