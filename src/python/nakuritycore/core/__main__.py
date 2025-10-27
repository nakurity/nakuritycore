import inspect
import sys
import traceback
import ast
from types import FunctionType

from ..data.config.tracer import TracerConfig
from ..data.config.logging import LoggingConfig
from ..utils.tracer import Tracer
from ..utils.logging import Logger
from .nakurity import NakurityRule, NakurityCustomRule, NakurityDocRule, NakurityTypeRule


class Nakurity:
    _registry = []  # list of (obj, metadata)
    _compile_registry = []
    _rules = []

    def __init__(self, logger=Logger()):
        self.tracer = Tracer(TracerConfig())
        self.logging = logger

    # ------------------------------------------------------------
    #  DECORATORS
    # ------------------------------------------------------------
    @classmethod
    def compile(cls, text: str = None):
        """Marks this object for compile-time validation (runs before runtime)."""
        def decorator(obj):
            entry = {
                "obj": obj,
                "expect": text.strip() if text else None,
                "stage": "compile"
            }
            cls._compile_registry.append(entry)
            cls._registry.append(entry)
            return obj
        return decorator
    
    @classmethod
    def expect(cls, text: str):
        """Defines runtime expectations for a function or class."""
        def decorator(obj):
            cls._registry.append({
                "obj": obj,
                "expect": text.strip(),
                "comment": None,
                "require": [],
                "guard": None
            })
            return obj
        return decorator

    @classmethod
    def comment(cls, text: str):
        """
        Attach a human-readable hint for debugging.
        Adds descriptive comment to a previously defined function/class.
        """
        def decorator(obj):
            # If already registered via @expect, attach comment
            for entry in cls._registry:
                if entry["obj"] is obj:
                    entry["comment"] = text.strip()
                    break
            else:
                # Otherwise, register new with only comment
                cls._registry.append({
                    "obj": obj,
                    "expect": None,
                    "comment": text.strip(),
                    "require": [],
                    "guard": None
                })
            return obj
        return decorator

    @classmethod
    def require(cls, *names: str):
        """Require that specific identifiers or callables exist."""
        def decorator(obj):
            for entry in cls._registry:
                if entry["obj"] is obj:
                    entry["require"].extend(names)
                    break
            else:
                cls._registry.append({
                    "obj": obj,
                    "expect": None,
                    "comment": None,
                    "require": list(names),
                    "guard": None
                })
            return obj
        return decorator

    @classmethod
    def guard(cls, condition: str):
        """Ensure a condition evaluates true before runtime."""
        def decorator(obj):
            for entry in cls._registry:
                if entry["obj"] is obj:
                    entry["guard"] = condition
                    break
            else:
                cls._registry.append({
                    "obj": obj,
                    "expect": None,
                    "comment": None,
                    "require": [],
                    "guard": condition
                })
            return obj
        return decorator
    
    @classmethod
    def _compile_pass(cls, module):
        import inspect, ast

        for entry in cls._compile_registry:
            obj = entry["obj"]
            try:
                src = inspect.getsource(obj)
                tree = ast.parse(src)

                # run minimal static analysis checks
                func_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
                if not func_defs:
                    continue

                func = func_defs[0]
                args = [a.arg for a in func.args.args]
                if "expected_arg_count" in entry.get("expect", ""):
                    expected = int(entry["expect"].split("expected")[1].split()[0])
                    if len(args) != expected:
                        print(f"⚠️ [Nakurity.compile] {obj.__name__}: expected {expected} args, found {len(args)}")

            except Exception as e:
                print(f"💥 [Nakurity.compile] Failed to analyze {obj.__name__}: {e}")

    # ------------------------------------------------------------
    # RULE MANAGEMENT
    # ------------------------------------------------------------
    @classmethod
    def register_rule(cls, rule_cls: type[NakurityRule]):
        """Register a custom lint rule class."""
        cls._rules.append(rule_cls())

    def _register_default_rules(self):
        """Automatically register built-in rules."""
        self.register_rule(NakurityDocRule)
        self.register_rule(NakurityTypeRule)
        self.register_rule(NakurityCustomRule)

    # ------------------------------------------------------------
    #  MAIN LINT ENTRYPOINT
    # ------------------------------------------------------------
    def lint(self):
        self.logging.debug("[Nakurity] 🧠 Pre-runtime lint initiated...\n")

        self._had_warnings = False

        for entry in Nakurity._registry:
            self._analyze_entry(entry)
            self._run_extra_rules(entry)

        if self._had_warnings:
            self.logging.debug("\n⚠️  Nakurity lint completed with warnings.\n")
        else:
            self.logging.debug("\n✅ Nakurity lint completed successfully.\n")

    def _run_extra_rules(self, entry):
        obj = entry["obj"]
        for rule in self._rules:
            try:
                ok = rule.check(entry, obj, self.logging)
                if not ok:
                    self._had_warnings = True
            except Exception as e:
                self._had_warnings = True
                self.logging.debug(f"💥 Rule {rule.name} failed on {obj.__name__}: {e}")

    # ------------------------------------------------------------
    #  LINT HANDLERS
    # ------------------------------------------------------------
    def _analyze_entry(self, entry):
        obj = entry["obj"]
        name = getattr(obj, "__name__", "<unknown>")
        kind = "class" if inspect.isclass(obj) else "function"
        comment = entry.get("comment")
        expect = entry.get("expect")
        requires = entry.get("require")
        guard = entry.get("guard")

        self.logging.debug(f"🔍 Inspecting {kind}: {name}")
        if comment:
            self.logging.debug(f"   💬 {comment}")
        if expect:
            self.logging.debug(f"   📋 Expectations defined.")
        if requires:
            self.logging.debug(f"   📦 Requires: {', '.join(requires)}")
        if guard:
            self.logging.debug(f"   🧩 Guard: {guard}")
        self.logging.debug("")

        # --- Requirement check ---
        self._check_requirements(entry, name)

        # --- Guard check ---
        if guard:
            self._check_guard(guard, name)

        # --- Expectation check ---
        if expect:
            rules = self._parse_expectations(expect)
            self._static_check(entry, rules)
            self._simulate_runtime(entry, rules)

    # ------------------------------------------------------------
    #  REQUIRE / GUARD / PARSE / CHECK
    # ------------------------------------------------------------

    def _check_guard(self, entry):
        obj_name = entry["obj"].__name__
        cond = entry["guard"]
        try:
            ok = eval(cond, globals())
            if not ok:
                msg = f"⚠️ Guard failed for {obj_name}: {cond}"
                self.logging.debug(msg)
                if entry.get("comment"):
                    self.logging.debug(f"   💡 Hint: {entry['comment']}")
                return False
        except Exception as e:
            self.logging.debug(f"💥 Guard error in {obj_name}: {cond} -> {e}")
            if entry.get("comment"):
                self.logging.debug(f"   💡 Hint: {entry['comment']}")
            return False
        return True
    
    def _check_requirements(self, entry, obj_name):
        for name in entry["require"]:
            if name not in globals() and name not in sys.modules:
                self.logging.debug(f"⚠️ {obj_name}: required '{name}' missing.")
                self._had_warnings = True
                if entry.get("comment"):
                    self.logging.debug(f"   💡 Hint: {entry['comment']}")
            else:
                self.logging.debug(f"✅ {obj_name}: found required dependency '{name}'.")

    def _parse_expectations(self, text: str) -> dict:
        """
        Smart Parser that handles:
            - expects N args: ...
            - must call foo()
            - should not raise
            - returns <type>
            - performs <action>
        """
        rules = {"args": [], "return": None, "must_call": [], "no_exceptions": False, "perform": None}
        for line in text.splitlines():
            line = line.strip().lower()
            if not line:
                continue
            if "arg" in line and ":" in line:
                parts = line.split(":", 1)[1]
                args = [a.strip() for a in parts.replace(",", " ").split() if a.strip()]
                rules["args"].extend(args)
            elif line.startswith("expects"):
                num = [int(s) for s in line.split() if s.isdigit()]
                if num:
                    rules["expected_arg_count"] = num[0]
            elif "return" in line:
                rules["return"] = line.split("return")[-1].strip()
            elif "should not raise" in line or "no exception" in line:
                rules["no_exceptions"] = True
            elif "must call" in line:
                fn = line.split("must call")[-1].strip().replace("()", "")
                rules["must_call"].append(fn)
            elif "perform" in line:
                rules["perform"] = line.split("perform")[-1].strip()
        return rules

    def _static_check(self, entry, rules):
        obj = entry["obj"]
        name = obj.__name__

        if isinstance(obj, FunctionType):
            sig = inspect.signature(obj)
            if "expected_arg_count" in rules and len(sig.parameters) != rules["expected_arg_count"]:
                self._had_warnings = True
                self.logging.debug(f"⚠️ {name}: expected {rules['expected_arg_count']} args, found {len(sig.parameters)}")
            if rules["args"] and set(rules["args"]) != set(sig.parameters.keys()):
                self._had_warnings = True
                self.logging.debug(f"⚠️ {name}: arg names mismatch -> expected {rules['args']}, got {list(sig.parameters.keys())}")
            if rules["return"] and sig.return_annotation is inspect.Signature.empty:
                self._had_warnings = True
                self.logging.debug(f"⚠️ {name}: missing return annotation (expected {rules['return']})")
        elif inspect.isclass(obj):
            methods = inspect.getmembers(obj, predicate=inspect.isfunction)
            if not methods:
                self._had_warnings = True
                self.logging.debug(f"⚠️ {name}: class has no methods.")

    # ------------------------------------------------------------
    #  RUNTIME SIMULATION
    # ------------------------------------------------------------
    def _simulate_runtime(self, entry, rules):
        obj = entry["obj"]
        if not isinstance(obj, FunctionType):
            return

        sig = inspect.signature(obj)
        args = [self._dummy_value(p) for p in sig.parameters.values()]

        called_functions = set()

        try:
            src = inspect.getsource(obj)
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    called_functions.add(node.func.id)
        except Exception as e:
            self._had_warnings = True
            self.logging.debug(f"⚠️ {obj.__name__}: AST inspection failed ({e})")

        # --- must_call early static detection ---
        for required_call in rules.get("must_call", []):
            if required_call not in called_functions:
                # We'll still trace runtime, but warn early if call is commented out
                src_preview = inspect.getsource(obj)
                if f"# {required_call}" in src_preview:
                    self._had_warnings = True
                    self.logging.debug(
                        f"⚠️ {obj.__name__}: found commented-out '{required_call}()' — "
                        f"call is ignored at runtime."
                    )

        # Local tracer to capture all function calls
        def trace_calls(frame, event, arg):
            if event == "call":
                called_functions.add(frame.f_code.co_name)
            return trace_calls

        try:
            sys.settrace(trace_calls)
            self.tracer.trace(inspect.currentframe(), "call", None)
            result = obj(*args)
            self.tracer.trace(inspect.currentframe(), "return", result)
        except Exception as e:
            self._had_warnings = True
            msg = f"💥 {obj.__name__}: raised {type(e).__name__} ({e})"
            if rules.get("no_exceptions"):
                msg += " [should not raise!]"
            self.logging.debug(msg)
            if entry.get("comment"):
                self.logging.debug(f"   💡 Hint: {entry['comment']}")
            self._trace_root_cause()
        finally:
            sys.settrace(None)  # disable tracing

        # --- must_call verification (after runtime) ---
        for required_call in rules.get("must_call", []):
            if required_call not in called_functions:
                self._had_warnings = True
                self.logging.debug(f"⚠️ {obj.__name__}: did not call required function '{required_call}()'")
            else:
                self.logging.debug(f"✅ {obj.__name__}: called required function '{required_call}()'")

        # --- return type check ---
        if "return" in rules and rules["return"]:
            expected = rules["return"]
            if expected in ("int", "float", "str", "bool"):
                if not isinstance(result, eval(expected)):
                    self._had_warnings = True
                    self.logging.debug(f"⚠️ {obj.__name__}: returned {type(result).__name__}, expected {expected}")

    def _dummy_value(self, param):
        name = param.name.lower()
        if "path" in name or "file" in name:
            return "dummy.txt"
        if "count" in name or "num" in name or "id" in name:
            return 1
        if "flag" in name or name.startswith("is_"):
            return True
        return "x"

    def _trace_root_cause(self):
        tb = traceback.format_exc().strip().splitlines()
        if tb:
            self.logging.debug("🔎 Root cause trace:")
            for line in tb[-5:]:
                self.logging.debug(f"   {line}")

    def _report_failure(self, entry, e):
        name = entry["obj"].__name__
        self._had_warnings = True
        self.logging.debug(f"💥 Error analyzing {name}: {e}")
        if entry.get("comment"):
            self.logging.debug(f"   💡 Hint: {entry['comment']}")
        self._trace_root_cause()

# -------------------------------------------------------------------------
#  EXAMPLE USAGE
# -------------------------------------------------------------------------
# from nakurity.core import Nakurity, NakurityRequirement
#
# @Nakurity.expect("""
# Expect:
#   - takes 1 argument: x
#   - returns int
#   - should not raise exception
# """)
# @Nakurity.comment("Simple doubling function")
# def double(x: int) -> int:
#     return x * 2
#
# @Nakurity.expect("""
# Expect:
#   - takes 1 argument: name
#   - returns str
#   - must call greet
# """)
# @Nakurity.require("greet")
# @Nakurity.guard("'greet' in globals()")
# def say_hi(name: str) -> str:
#     greet(name)
#     return f"Hello, {name}"
#
# def greet(name: str):
#     return f"Hi {name}"
#
# if __name__ == "__main__":
#     NakurityRequirement(sys.modules[__name__])