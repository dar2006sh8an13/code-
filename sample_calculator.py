"""Sample calculator module to demonstrate autonomous debugging."""


def divide_numbers(a: float, b: float) -> float:
    """Divide a by b safely."""
    if b == 0:
        return 0.0
    return a / b
