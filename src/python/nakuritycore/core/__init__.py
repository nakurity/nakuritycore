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

    def _nakurity_import(name, globals=None, locals=None, fromlist=(), level=0):
        module = _orig_import(name, globals, locals, fromlist, level)

        # Only enforce on your namespaces
        if name.startswith("your_project.") or name.startswith("nakurity_"):
            try:
                Nakurity._compile_pass(module)
            except Exception as e:
                sys.stderr.write(f"[Nakurity] ⚠️ Compile-time checks failed for {name}: {e}\n")

        return module

    builtins.__import__ = [_nakurity_guarded_import, _nakurity_import]
    builtins._nakurity_import_hook_installed = True

__all__ = ["Nakurity", "NakurityRequirement"]