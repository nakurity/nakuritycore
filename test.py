from nakuritycore.core.nakuly import Nakuly

nakuly = Nakuly()
nakuly.enable()


@nakuly.expect("expects 2 args: x, y; returns int")
@nakuly.comment("Adds two integers.")
def add(x: int, y: int) -> int:
    """Add two numbers.

    Args:
        x (int): First number
        y (int): Second number
    Returns:
        int: Sum
    """
    return x + y


@nakuly.comment("Broken example — missing docstring and type hints")
def broken(x, y):
    return x + y


nakuly.analyze()
nakuly.report_summary()
nakuly.disable()
