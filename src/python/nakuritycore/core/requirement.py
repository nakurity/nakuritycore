from .__main__ import Nakurity
from types import ModuleType

import inspect

# -------------------------------------------------------------------------
#  ENFORCEMENT WRAPPER
# -------------------------------------------------------------------------
class NakurityRequirement:
    """
    Enforces Nakurity discipline:
      - Every function and class in the module must have at least one @Nakurity.* decorator.
      - Automatically triggers Nakurity.lint() to validate expectations and guards.
    """

    def __init__(self, module: ModuleType):
        self.module = module
        self._verify_all_decorated()
        self._run_lint()

    def _verify_all_decorated(self):
        defined_objs = [
            obj for _, obj in inspect.getmembers(self.module)
            if inspect.isfunction(obj) or inspect.isclass(obj)
        ]
        registered_objs = [entry["obj"] for entry in Nakurity._registry]

        for obj in defined_objs:
            if obj not in registered_objs:
                print(f"🚫 [NakurityRequirement] {obj.__name__} is missing Nakurity decorators.")
                print("    → Use @Nakurity.expect / @Nakurity.comment / @Nakurity.require / @Nakurity.guard")
                print()

    def _run_lint(self):
        print("[NakurityRequirement] Running enforced lint checks...\n")
        Nakurity().lint()

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