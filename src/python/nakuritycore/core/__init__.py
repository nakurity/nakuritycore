import builtins
import sys
from types import ModuleType

from .__main__ import Nakurity
from .requirement import NakurityRequirement  # adjust path if needed

# Prevent double-installation
if not getattr(builtins, "_nakurity_import_hook_installed", False):

    _orig_import = builtins.__import__

    def _nakurity_guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        module = _orig_import(name, globals, locals, fromlist, level)

        # enforce Nakurity checks only on your own packages, not stdlib or deps
        if name.startswith("nakurity_") or name.startswith("nakuritycore."):
            try:
                if isinstance(module, ModuleType):
                    NakurityRequirement(module)
            except Exception as e:
                # soft fail — Nakurity should warn, not crash imports
                sys.stderr.write(f"[Nakurity] Enforcement failed for {name}: {e}\n")

        return module

    # Prevent double-installation

    builtins.__import__ = _nakurity_guarded_import
    builtins._nakurity_import_hook_installed = True

__all__ = ["Nakurity", "NakurityRequirement"]