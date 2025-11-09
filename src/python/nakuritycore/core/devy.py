# devy.py
from __future__ import annotations
import ast
import inspect
import sys
import time
import tracemalloc
import threading
import types
import traceback
from typing import Any, Callable, Dict, List, Optional

CompileChecker = Callable[[ast.AST, str], Optional[ast.AST]]
RuntimeChecker = Callable[[types.FrameType, str, Any], None]


class Devy:
    """
    Devy — unified developer guard and analyzer.
    Wraps PyGuard-style import/runtime tracing + Nakurity-style decorators.
    """

    _registry: List[Dict[str, Any]] = []
    _compile_registry: List[Dict[str, Any]] = []
    _rules: List[Any] = []

    def __init__(self, compile_checker: CompileChecker = None,
                 runtime_checker: RuntimeChecker = None,
                 logger: Optional[Callable[[str], None]] = None):
        from pyguard import PyGuard  # you can import your above code here

        self.logger = logger or (lambda msg: print(msg, flush=True))
        self.guard = PyGuard(
            compile_checker=compile_checker or self._default_compile_checker,
            runtime_checker=runtime_checker or self._default_runtime_checker,
        )

        # runtime metrics
        self._start_time = None
        self._enabled = False

    # ------------------------------------------------------------
    #  🔹 Lifecycle Controls
    # ------------------------------------------------------------
    def enable(self):
        self.guard.enable_all()
        self._start_time = time.perf_counter()
        tracemalloc.start()
        self._enabled = True
        self.logger("🟢 Devy active — import hooks + tracing enabled.")

    def disable(self):
        self.guard.disable_all()
        tracemalloc.stop()
        self._enabled = False
        self.logger("🔴 Devy disabled — tracing stopped.")

    # ------------------------------------------------------------
    #  🔹 Decorators (like Nakurity)
    # ------------------------------------------------------------
    @classmethod
    def compile_check(cls, rule: str = None):
        def decorator(obj):
            entry = {"obj": obj, "rule": rule, "stage": "compile"}
            cls._compile_registry.append(entry)
            cls._registry.append(entry)
            return obj
        return decorator

    @classmethod
    def expect(cls, text: str):
        def decorator(obj):
            cls._registry.append({
                "obj": obj, "expect": text.strip(),
                "comment": None, "require": [], "guard": None
            })
            return obj
        return decorator

    @classmethod
    def comment(cls, text: str):
        def decorator(obj):
            for entry in cls._registry:
                if entry["obj"] is obj:
                    entry["comment"] = text.strip()
                    break
            else:
                cls._registry.append({
                    "obj": obj, "expect": None,
                    "comment": text.strip(), "require": [], "guard": None
                })
            return obj
        return decorator

    @classmethod
    def require(cls, *names: str):
        def decorator(obj):
            for entry in cls._registry:
                if entry["obj"] is obj:
                    entry["require"].extend(names)
                    break
            else:
                cls._registry.append({
                    "obj": obj, "expect": None,
                    "comment": None, "require": list(names), "guard": None
                })
            return obj
        return decorator

    @classmethod
    def guard(cls, condition: str):
        def decorator(obj):
            for entry in cls._registry:
                if entry["obj"] is obj:
                    entry["guard"] = condition
                    break
            else:
                cls._registry.append({
                    "obj": obj, "expect": None,
                    "comment": None, "require": [], "guard": condition
                })
            return obj
        return decorator

    # ------------------------------------------------------------
    #  🔹 Compile-Time / Static Checks
    # ------------------------------------------------------------
    @staticmethod
    def _default_compile_checker(tree: ast.AST, filename: str) -> Optional[ast.AST]:
        """Reject 'exec' or 'eval' and inject __DEVY__ flag."""
        class BadCallVisitor(ast.NodeVisitor):
            def __init__(self):
                self.errors = []
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval"}:
                    self.errors.append((node.lineno, node.func.id))
                self.generic_visit(node)

        v = BadCallVisitor()
        v.visit(tree)
        if v.errors:
            bads = ", ".join(f"{name}@{line}" for line, name in v.errors)
            raise SyntaxError(f"Devy blocked unsafe call(s): {bads} in {filename}")

        assign = ast.Assign(
            targets=[ast.Name(id="__DEVY__", ctx=ast.Store())],
            value=ast.Constant(True),
        )
        ast.fix_missing_locations(assign)
        if isinstance(tree, ast.Module):
            tree.body.insert(0, assign)
        return tree

    # ------------------------------------------------------------
    #  🔹 Runtime Hook / Live Checker
    # ------------------------------------------------------------
    @staticmethod
    def _default_runtime_checker(frame: types.FrameType, event: str, arg: Any):
        """Simple runtime protection example."""
        if event == "call" and frame.f_code.co_name == "danger":
            raise RuntimeError("Function 'danger' blocked by Devy runtime guard.")

    # ------------------------------------------------------------
    #  🔹 Analysis / Lint Execution
    # ------------------------------------------------------------
    def analyze(self):
        """Run static checks for registered functions/classes."""
        self.logger("🧠 [Devy] Running analysis...")
        for entry in self._registry:
            try:
                self._analyze_entry(entry)
            except Exception as e:
                self.logger(f"💥 Analysis error on {entry['obj'].__name__}: {e}")
        self.logger("✅ [Devy] Analysis finished.")

    def _analyze_entry(self, entry):
        obj = entry["obj"]
        name = getattr(obj, "__name__", "<unnamed>")
        self.logger(f"🔍 Inspecting {name}")

        # requirement check
        for dep in entry.get("require", []):
            if dep not in globals() and dep not in sys.modules:
                self.logger(f"⚠️ Missing dependency: {dep}")
        # guard check
        if entry.get("guard"):
            try:
                ok = eval(entry["guard"], globals())
                if not ok:
                    self.logger(f"⚠️ Guard failed for {name}: {entry['guard']}")
            except Exception as e:
                self.logger(f"💥 Guard evaluation error in {name}: {e}")

        # expectation static analysis
        expect = entry.get("expect")
        if expect and inspect.isfunction(obj):
            self._check_signature(obj, expect)

    def _check_signature(self, func, expect: str):
        sig = inspect.signature(func)
        if "expects" in expect and any(s.isdigit() for s in expect):
            try:
                num = int([s for s in expect.split() if s.isdigit()][0])
                if len(sig.parameters) != num:
                    self.logger(f"⚠️ {func.__name__}: expected {num} args, found {len(sig.parameters)}")
            except Exception:
                pass

    # ------------------------------------------------------------
    #  🔹 Performance Profiling
    # ------------------------------------------------------------
    def profile_runtime(self):
        """Rough performance report since enable()."""
        if not self._enabled:
            self.logger("⚠️ Devy is not enabled.")
            return
        duration = time.perf_counter() - self._start_time
        cur, peak = tracemalloc.get_traced_memory()
        self.logger(f"⏱️  Uptime: {duration:.2f}s | Mem: {cur/1e6:.2f}MB (peak {peak/1e6:.2f}MB)")

    # ------------------------------------------------------------
    #  🔹 Rule Registration
    # ------------------------------------------------------------
    @classmethod
    def register_rule(cls, rule_cls):
        cls._rules.append(rule_cls())
