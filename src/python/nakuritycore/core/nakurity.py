import inspect
import types
from abc import ABC, abstractmethod

class NakurityRule(ABC):
    """Base class for all Nakurity validation rules."""

    name: str = "UnnamedRule"
    description: str = "No description provided."

    @abstractmethod
    def check(self, entry, obj, logger) -> bool:
        """Return True if passes, False if fails."""
        ...


class NakurityDocRule(NakurityRule):
    name = "DocstringRule"
    description = "Ensure all functions and classes have docstrings."

    def check(self, entry, obj, logger):
        doc = inspect.getdoc(obj)
        if not doc:
            logger.debug(f"⚠️ {obj.__name__}: missing docstring.")
            return False

        # Optional: enforce docstring structure
        if inspect.isfunction(obj) or isinstance(obj, types.FunctionType) and "Args:" not in doc and "Parameters:" not in doc:
            logger.debug(f"⚠️ {obj.__name__}: docstring missing 'Args:' section.")
        if "return" in inspect.signature(obj).parameters and "Returns:" not in doc:
            logger.debug(f"⚠️ {obj.__name__}: docstring missing 'Returns:' section.")
        return True


class NakurityTypeRule(NakurityRule):
    name = "TypeHintRule"
    description = "Ensure functions and methods use consistent type annotations."

    def check(self, entry, obj, logger):
        if inspect.isfunction(obj) or isinstance(obj, types.FunctionType):
            return True
        sig = inspect.signature(obj)
        ok = True
        for name, param in sig.parameters.items():
            if param.annotation is inspect.Signature.empty:
                logger.debug(f"⚠️ {obj.__name__}: parameter '{name}' missing type annotation.")
                ok = False
        if sig.return_annotation is inspect.Signature.empty:
            logger.debug(f"⚠️ {obj.__name__}: missing return type annotation.")
            ok = False
        return ok


class NakurityCustomRule(NakurityRule):
    """Example rule: Ensure function names follow snake_case."""

    name = "NamingConventionRule"
    description = "Function names must be snake_case."

    def check(self, entry, obj, logger):
        if inspect.isfunction(obj) or isinstance(obj, types.FunctionType) and not obj.__name__.islower():
            logger.debug(f"⚠️ {obj.__name__}: name not snake_case.")
            return False
        return True

# ------------------------
# Example implementation
# ------------------------
#
# class NakurityReturnRule(NakurityRule):
#     name = "ReturnTypeRuntimeRule"
#     description = "Ensure return value matches declared annotation at runtime."

#     def check(self, entry, obj, logger):
#         if not isinstance(obj, FunctionType):
#             return True
#         sig = inspect.signature(obj)
#         if sig.return_annotation is inspect.Signature.empty:
#             return True

#         try:
#             dummy_args = ["x" for _ in sig.parameters]
#             result = obj(*dummy_args)
#             if not isinstance(result, eval(sig.return_annotation.__name__)):
#                 logger.debug(f"⚠️ {obj.__name__}: returned {type(result).__name__}, expected {sig.return_annotation}.")
#                 return False
#         except Exception as e:
#             logger.debug(f"💥 {obj.__name__}: failed during runtime type check ({e})")
#             return False
#         return True


# # Register it
# Nakurity.register_rule(NakurityReturnRule)

# ------------------------
# Example usage
# ------------------------
# @Nakurity.expect("""
# Expect:
#   - takes 1 argument: x
#   - returns int
#   - should not raise exception
# """)
# @Nakurity.comment("Simple doubling function")
# def double(x: int) -> int:
#     """Doubles a number.
#    
#     Args:
#         x (int): input value
#     Returns:
#         int: doubled value
#     """
#     return x * 2
#
#
# # Run the lint system
# if __name__ == "__main__":
#     Nakurity().lint()
