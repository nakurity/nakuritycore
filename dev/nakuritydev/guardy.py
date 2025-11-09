"""
pyguard.py

Lightweight library to:
 - Perform compile-time checks / AST transforms via import hooks and wrapped compile()
 - Perform runtime checks via sys.settrace()

Limitations:
 - Does not (and cannot) intercept native C extension internals.
 - Tracing introduces overhead; don't use in tight production loops.
 - Some dynamic import/load paths may bypass meta_path; can be extended.
"""

from __future__ import annotations
import ast
import builtins
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import types
import threading
import traceback
from typing import Callable, Optional, Any, Dict

# ---- User-extensible checks ----
# Compile-time checker accepts AST and file path, raises Exception to block compilation
CompileChecker = Callable[[ast.AST, str], Optional[ast.AST]]
# Runtime checker called before each executed line: frame, event, arg -> may raise or log
RuntimeChecker = Callable[[types.FrameType, str, Any], None]


# ---- Default example compile checker ----
def example_compile_checker(tree: ast.AST, filename: str) -> Optional[ast.AST]:
    """
    Example: reject code that uses 'exec' or 'eval' at compile-time,
    and also inject a small AST transform: add a module-level __PYGUARD__ flag.
    """
    class ExecFindingVisitor(ast.NodeVisitor):
        def __init__(self):
            self.found = False
            self.nodes = []

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval"):
                self.found = True
                self.nodes.append((node.lineno, node.func.id))
            self.generic_visit(node)

    v = ExecFindingVisitor()
    v.visit(tree)
    if v.found:
        lines = ", ".join(f"{name}@{ln}" for ln, name in [(n[0], n[1]) for n in v.nodes]) if v.nodes else "exec/eval"
        raise SyntaxError(f"Blocked use of exec/eval in {filename}: {lines}")

    # Inject __PYGUARD__ = True at top of module (example transform)
    assign = ast.Assign(
        targets=[ast.Name(id="__PYGUARD__", ctx=ast.Store())],
        value=ast.Constant(value=True),
    )
    ast.fix_missing_locations(assign)
    if isinstance(tree, ast.Module):
        tree.body.insert(0, assign)

    return tree


# ---- Default example runtime checker ----
def example_runtime_checker(frame: types.FrameType, event: str, arg: Any) -> None:
    """
    Warn if code attempts to call open() on write in a sensitive file; example only.
    This function should be fast — it's called frequently under tracing.
    """
    # As an example: if a function named 'danger' is called, raise an error
    if event == "call":
        name = frame.f_code.co_name
        if name == "danger":
            raise RuntimeError("Call to function 'danger' is blocked by pyguard runtime checks.")


# ---- AST import hook / loader wrapper ----
class GuardingLoader(importlib.abc.Loader):
    def __init__(self, orig_loader: importlib.abc.Loader, compile_checker: CompileChecker):
        self.orig_loader = orig_loader
        self.compile_checker = compile_checker

    def create_module(self, spec):
        # Defer to original loader if it implements create_module
        if hasattr(self.orig_loader, "create_module"):
            return self.orig_loader.create_module(spec)
        return None

    def exec_module(self, module):
        # If the original loader can get source, use it and apply checks/transforms.
        source = None
        if hasattr(self.orig_loader, "get_source"):
            try:
                source = self.orig_loader.get_source(module.__spec__.name)
            except Exception:
                source = None

        if source is None:
            # Fall back to delegating exec_module if we can't get source
            return self.orig_loader.exec_module(module)

        filename = getattr(module, "__spec__", None) and module.__spec__.origin or "<unknown>"
        try:
            tree = ast.parse(source, filename=filename)
            new_tree = self.compile_checker(tree, filename) if self.compile_checker else tree
            if new_tree is None:
                # Checker chose to skip / allow unchanged
                codeobj = compile(tree, filename, "exec")
            else:
                ast.fix_missing_locations(new_tree)
                codeobj = compile(new_tree, filename, "exec")
        except Exception as e:
            # Surface compile-time errors as ImportError for clearer import-time feedback
            tb = traceback.format_exc()
            raise ImportError(f"pyguard compile-time check failed for {filename}:\n{tb}") from e

        # execute compiled code in module namespace
        exec(codeobj, module.__dict__)


class GuardingFinder(importlib.abc.MetaPathFinder):
    def __init__(self, compile_checker: CompileChecker):
        self.compile_checker = compile_checker
        # Remember orig finders that we will wrap so we can delegate
        self._delegates = []

    def find_spec(self, fullname, path, target=None):
        # Walk through existing finders and try to find a loader we can wrap.
        for finder in sys.meta_path:
            if finder is self:
                continue
            # Some finders are importlib._bootstrap_external.PathFinder etc.
            try:
                spec = finder.find_spec(fullname, path, target)
            except Exception:
                spec = None
            if spec and spec.loader:
                # Only wrap if source-based loader exists
                if hasattr(spec.loader, "get_source"):
                    wrapped_loader = GuardingLoader(spec.loader, self.compile_checker)
                    spec.loader = wrapped_loader
                    return spec
                else:
                    # Cannot get source — delegate without wrapping
                    return spec
        return None


# ---- Wrapping builtins.compile / exec / eval so dynamic compile goes through checker ----
_original_compile = builtins.compile
_original_eval = builtins.eval
_original_exec = builtins.exec

def make_compile_wrapper(compile_checker: CompileChecker):
    def compile_wrapper(source, filename, mode, flags=0, dont_inherit=False, optimize=-1):
        # If source is AST already, allow checker to run on AST
        if isinstance(source, ast.AST):
            tree = source
            if compile_checker:
                tree = compile_checker(tree, filename) or tree
            ast.fix_missing_locations(tree)
            return _original_compile(tree, filename, mode, flags, dont_inherit, optimize)
        # If source is a string, parse it to AST, check, then recompile
        if isinstance(source, str):
            tree = ast.parse(source, filename)
            if compile_checker:
                tree = compile_checker(tree, filename) or tree
            ast.fix_missing_locations(tree)
            return _original_compile(tree, filename, mode, flags, dont_inherit, optimize)
        # fallback
        return _original_compile(source, filename, mode, flags, dont_inherit, optimize)
    return compile_wrapper

def make_exec_eval_wrappers(compile_checker):
    def exec_wrapper(source, globals=None, locals=None):
        # If string, compile via wrapper first
        if isinstance(source, str):
            c = make_compile_wrapper(compile_checker)(source, "<string>", "exec")
            return _original_exec(c, globals, locals)
        return _original_exec(source, globals, locals)

    def eval_wrapper(source, globals=None, locals=None):
        if isinstance(source, str):
            c = make_compile_wrapper(compile_checker)(source, "<string>", "eval")
            return _original_eval(c, globals, locals)
        return _original_eval(source, globals, locals)

    return exec_wrapper, eval_wrapper


# ---- Runtime tracing manager ----
class RuntimeTracer:
    def __init__(self, runtime_checker: RuntimeChecker):
        self.runtime_checker = runtime_checker
        self._enabled = False
        self._thread_local = threading.local()

    def _global_trace(self, frame: types.FrameType, event: str, arg):
        # Lightweight guard: ignore frames inside this module to avoid recursion
        if frame.f_globals.get("__name__") == __name__:
            return None
        try:
            # Call user's checker; it may raise to stop execution
            self.runtime_checker(frame, event, arg)
        except Exception:
            # Re-raise as a runtime error but keep stack info
            raise
        # Return itself for local tracing if needed for 'line' events
        return self._local_trace

    def _local_trace(self, frame: types.FrameType, event: str, arg):
        # Called frequently; be minimalistic
        try:
            self.runtime_checker(frame, event, arg)
        except Exception:
            raise
        return self._local_trace

    def start(self):
        if not self._enabled:
            sys.settrace(self._global_trace)
            # Also trace new threads
            threading.settrace(self._global_trace)
            self._enabled = True

    def stop(self):
        if self._enabled:
            sys.settrace(None)
            threading.settrace(None)
            self._enabled = False


# ---- Public API ----
class PyGuard:
    def __init__(self,
                 compile_checker: CompileChecker = example_compile_checker,
                 runtime_checker: RuntimeChecker = example_runtime_checker):
        self.compile_checker = compile_checker
        self.runtime_checker = runtime_checker
        self._finder: Optional[GuardingFinder] = None
        self._tracer: Optional[RuntimeTracer] = None
        self._enabled = False
        self._patched = False

    def enable_import_guard(self):
        if self._finder is not None:
            return
        finder = GuardingFinder(self.compile_checker)
        # Insert at front so it takes precedence
        sys.meta_path.insert(0, finder)
        self._finder = finder

    def disable_import_guard(self):
        if self._finder is None:
            return
        try:
            sys.meta_path.remove(self._finder)
        except ValueError:
            pass
        self._finder = None

    def patch_builtins(self):
        if self._patched:
            return
        builtins.compile = make_compile_wrapper(self.compile_checker)
        builtins.exec, builtins.eval = make_exec_eval_wrappers(self.compile_checker)
        self._patched = True

    def unpatch_builtins(self):
        if not self._patched:
            return
        builtins.compile = _original_compile
        builtins.exec = _original_exec
        builtins.eval = _original_eval
        self._patched = False

    def start_runtime_tracer(self):
        if self._tracer is not None:
            return
        self._tracer = RuntimeTracer(self.runtime_checker)
        self._tracer.start()

    def stop_runtime_tracer(self):
        if self._tracer is None:
            return
        self._tracer.stop()
        self._tracer = None

    def enable_all(self):
        self.enable_import_guard()
        self.patch_builtins()
        self.start_runtime_tracer()
        self._enabled = True

    def disable_all(self):
        self.disable_import_guard()
        self.unpatch_builtins()
        self.stop_runtime_tracer()
        self._enabled = False


# ---- CLI for quick demo ----
def _demo():
    print("Starting pyguard demo. Import guard + builtin patch + tracer enabled.")
    g = PyGuard()
    g.enable_all()

    # Attempt to import a module that uses eval -> should be blocked by example_compile_checker.
    # We'll create a temporary module file.
    import tempfile, os
    tmpdir = tempfile.mkdtemp(prefix="pyguard_demo_")
    modpath = os.path.join(tmpdir, "mymod.py")
    with open(modpath, "w") as f:
        f.write("def danger():\n    print('in danger')\n\nx = eval('2+2')\n")

    sys.path.insert(0, tmpdir)
    try:
        try:
            import mymod  # should trigger checker and raise ImportError
        except Exception as e:
            print("Import blocked as expected:", type(e).__name__, e)
    finally:
        sys.path.remove(tmpdir)
        # cleanup not strictly necessary for demo

    # Test runtime tracer
    def danger():
        print("this would be blocked at runtime if named 'danger'")

    try:
        danger()
    except Exception as e:
        print("Runtime blocker caught:", e)

    # cleanup
    g.disable_all()
    print("Demo finished.")


if __name__ == "__main__":
    _demo()
