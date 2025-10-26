import inspect
import sys
from types import FunctionType

from ..data.config.tracer import TracerConfig
from ..utils.tracer import Tracer


class Nakurity:
    _registry = []  # list of (obj, metadata)

    def __init__(self):
        pass

    # ------------------------------------------------------------
    #  DECORATORS
    # ------------------------------------------------------------
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
        """Adds descriptive comment to a previously defined function/class."""
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

    # ------------------------------------------------------------
    #  MAIN LINT ENTRYPOINT
    # ------------------------------------------------------------
    def lint(self):
        cfg = TracerConfig()
        tracer = Tracer(cfg)
        print("[Nakurity] 🧠 Pre-runtime lint initiated...\n")

        for entry in Nakurity._registry:
            self._analyze_entry(entry, tracer)

        print("\n✅ Nakurity lint completed successfully.\n")

    # ------------------------------------------------------------
    #  LINT HANDLERS
    # ------------------------------------------------------------
    def _analyze_entry(self, entry, tracer):
        obj = entry["obj"]
        name = getattr(obj, "__name__", "<unknown>")
        kind = "class" if inspect.isclass(obj) else "function"
        comment = entry.get("comment")
        expect = entry.get("expect")
        requires = entry.get("require")
        guard = entry.get("guard")

        print(f"🔍 Inspecting {kind}: {name}")
        if comment:
            print(f"   💬 {comment}")
        if expect:
            print(f"   📋 Expectations defined.")
        if requires:
            print(f"   📦 Requires: {', '.join(requires)}")
        if guard:
            print(f"   🧩 Guard: {guard}")
        print()

        # --- Requirement check ---
        self._check_requirements(requires, name, tracer)

        # --- Guard check ---
        if guard:
            self._check_guard(guard, name, tracer)

        # --- Expectation check ---
        if expect:
            rules = self._parse_expectations(expect)
            self._static_check(obj, rules, tracer)
            self._simulate_runtime(obj, rules, tracer)

    # ------------------------------------------------------------
    #  REQUIRE / GUARD / PARSE / CHECK
    # ------------------------------------------------------------
    def _check_requirements(self, requires, obj_name, tracer):
        for name in requires:
            if name not in globals() and name not in sys.modules:
                tracer._write(f"⚠️ {obj_name}: required '{name}' not found in current scope")

    def _check_guard(self, condition, obj_name, tracer):
        try:
            ok = eval(condition, globals())
            if not ok:
                tracer._write(f"⚠️ {obj_name}: guard condition failed -> {condition}")
        except Exception as e:
            tracer._write(f"💥 {obj_name}: guard condition error '{condition}' -> {e}")

    def _parse_expectations(self, text: str) -> dict:
        rules = {"args": [], "return": None, "no_exceptions": False, "must_call": []}
        for line in text.splitlines():
            line = line.strip().lower()
            if not line:
                continue
            if "argument" in line and ":" in line:
                args = line.split(":")[1].strip().replace(",", " ").split()
                rules["args"].extend(args)
            elif line.startswith("takes"):
                n = [int(s) for s in line.split() if s.isdigit()]
                if n:
                    rules["args_expected_count"] = n[0]
            elif "return" in line:
                rules["return"] = line.split("return")[-1].strip()
            elif "no exception" in line or "should not raise" in line:
                rules["no_exceptions"] = True
            elif "must call" in line:
                fn = line.split("must call")[-1].strip()
                rules["must_call"].append(fn)
        return rules

    def _static_check(self, obj, rules, tracer):
        if isinstance(obj, FunctionType):
            sig = inspect.signature(obj)
            if "args_expected_count" in rules and len(sig.parameters) != rules["args_expected_count"]:
                tracer._write(f"⚠️ {obj.__name__}: expected {rules['args_expected_count']} args, found {len(sig.parameters)}")
            if rules["args"] and set(rules["args"]) != set(sig.parameters.keys()):
                tracer._write(f"⚠️ {obj.__name__}: argument names mismatch -> expected {rules['args']} got {list(sig.parameters.keys())}")
            if rules["return"] and sig.return_annotation is inspect.Signature.empty:
                tracer._write(f"⚠️ {obj.__name__}: missing return annotation (expected {rules['return']})")
        elif inspect.isclass(obj):
            methods = inspect.getmembers(obj, predicate=inspect.isfunction)
            if not methods:
                tracer._write(f"⚠️ {obj.__name__}: class has no methods defined")

    # ------------------------------------------------------------
    #  RUNTIME SIMULATION
    # ------------------------------------------------------------
    def _simulate_runtime(self, obj, rules, tracer):
        if not isinstance(obj, FunctionType):
            return
        sig = inspect.signature(obj)
        fake_args = []
        for _, param in sig.parameters.items():
            if param.default is not inspect.Parameter.empty:
                fake_args.append(param.default)
            else:
                fake_args.append(self._dummy_value(param))
        try:
            tracer.trace(inspect.currentframe(), "call", None)
            result = obj(*fake_args)
            tracer.trace(inspect.currentframe(), "return", result)
            # Return check
            if rules["return"]:
                expected = rules["return"]
                if expected in ("int", "float", "str", "bool"):
                    if not isinstance(result, eval(expected)):
                        tracer._write(f"⚠️ {obj.__name__}: returned {type(result).__name__}, expected {expected}")
        except Exception as e:
            if rules.get("no_exceptions"):
                tracer._write(f"💥 {obj.__name__}: raised {type(e).__name__} but should not")
            else:
                tracer._write(f"ℹ️ {obj.__name__}: exception observed (allowed): {e}")

    def _dummy_value(self, param):
        name = param.name.lower()
        if "path" in name or "file" in name:
            return "dummy.txt"
        if "count" in name or "num" in name or "id" in name:
            return 1
        if "flag" in name or name.startswith("is_"):
            return True
        return "x"

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