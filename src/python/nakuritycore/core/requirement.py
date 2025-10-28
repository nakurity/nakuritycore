from .__main__ import Nakurity
from types import ModuleType
from ..utils.logging import Logger
from ..data.config.logging import LoggingConfig

import inspect

# -------------------------------------------------------------------------
#  ENFORCEMENT WRAPPER
# -------------------------------------------------------------------------
@Nakurity.expect("""
Expect:
    - takes 1 argument: x
    - returns int
    - should not raise exception
""")
class NakurityRequirement:
    """
    Enforces Nakurity discipline:
      - Every function and class in the module must have at least one @Nakurity.* decorator.
      - Automatically triggers Nakurity.lint() to validate expectations and guards.

      REQUIRES:
        - To be run after everything has been defined
    """

    def __init__(self, module: ModuleType, output_level: str = "INFO"):
        self.module = module
        self.output_level = output_level
        self.logging = Logger(
            name="NakurityRequirement",
            config=LoggingConfig(
                level=output_level,
            )
        )
        self._verify_all_decorated()
        self._run_lint()

    def _verify_all_decorated(self):
        """
        Verify that every user-defined function/class in the module has at least
        one Nakurity decorator registered.  Skip:
        - dunder names (internal)
        - objects from other modules
        - objects clearly from the typing module (e.g., NamedTuple / typing helpers)
        """
        defined_objs = []
        for _, obj in inspect.getmembers(self.module):
            # include only functions or classes AND only if defined in this module
            if (inspect.isfunction(obj) or inspect.isclass(obj)) and getattr(obj, "__module__", None) == self.module.__name__:
                # skip private/dunder items
                name = getattr(obj, "__name__", None)
                if not name or name.startswith("_"):
                    continue
                # skip typing internals (e.g., NamedTuple implementations brought in by typing)
                mod = getattr(obj, "__module__", "")
                if mod.startswith("typing") or mod.startswith("collections"):
                    continue
                defined_objs.append(obj)

        registered_objs = [entry["obj"] for entry in Nakurity._registry]

        for obj in defined_objs:
            if obj not in registered_objs:
                self.logging.debug(f"🚫 [NakurityRequirement] {obj.__name__} is missing Nakurity decorators.")
                self.logging.debug("    → Use @Nakurity.expect / @Nakurity.comment / @Nakurity.require / @Nakurity.guard")
                self.logging.debug("")
                raise Exception(f"{obj.__name__} is missing Nakurity decorators.")

    def _run_lint(self):
        self.logging.debug("[NakurityRequirement] Running enforced lint checks...\n")
        Nakurity(self.logging).lint()

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