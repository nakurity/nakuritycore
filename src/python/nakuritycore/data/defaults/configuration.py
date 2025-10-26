from dataclasses import dataclass, asdict, field, fields
from typing import Any, Dict, TypeVar, Type
from pathlib import Path

import json
import copy
import os

T = TypeVar("T", bound="DefaultConfig")

@dataclass
class DefaultConfig:
    """A reusable base config dataclass with helpful defaults."""
    name: str = "default"
    enabled: bool = True
    debug: bool = False
    version: str = "1.0.0"

    # Common filesystem anchor
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])

    # Arbitrary metadata
    meta: Dict[str, Any] = field(default_factory=dict)

    # --- Utility methods ---
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        return cls(**{f.name: data.get(f.name) for f in fields(cls)})

    @classmethod
    def from_json(cls: Type[T], path: str) -> T:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def save_json(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def clone(self: T, **overrides) -> T:
        """Return a shallow copy with optional overrides."""
        new = copy.copy(self)
        for k, v in overrides.items():
            setattr(new, k, v)
        return new

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} version={self.version!r}>"

# ------------------------------
# Example Usage
# ------------------------------
#
# @dataclass
# class DatabaseConfig(DefaultConfig):
#     host: str = "localhost"
#     port: int = 5432
#     user: str = "admin"
#     password: str = "password"
#
# # --------------------------------
# # Example Usage
# # --------------------------------
# #
# # db_cfg = DatabaseConfig(debug=True, meta={"env": "dev"})
# # print(db_cfg.to_json())
# #
# # copy_cfg = db_cfg.clone(port=3306)
# # copy_cfg.save_json("configs/db.json")