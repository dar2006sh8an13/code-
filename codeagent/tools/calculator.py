"""Safe calculator tool implementing arithmetic operations without unrestricted eval."""

import ast
import operator
from typing import Any, Union


class CalculatorError(Exception):
    """Raised when arithmetic evaluation fails."""
    pass


# Supported AST binary operators
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def add(a: float, b: float) -> float:
    """Add two numbers (a + b)."""
    return float(a) + float(b)


def subtract(a: float, b: float) -> float:
    """Subtract b from a (a - b)."""
    return float(a) - float(b)


def multiply(a: float, b: float) -> float:
    """Multiply two numbers (a * b)."""
    return float(a) * float(b)


def divide(a: float, b: float) -> float:
    """Divide a by b (a / b).

    Raises:
        CalculatorError: If b is zero.
    """
    if float(b) == 0.0:
        raise CalculatorError("Division by zero is undefined.")
    return float(a) / float(b)


def safe_eval_arithmetic(expression: str) -> float:
    """Safely evaluate an arithmetic string expression using Python's Abstract Syntax Tree (AST).

    Only allows basic numeric literals and arithmetic operators (+, -, *, /, //, %, **).
    Rejects any variable lookups, function calls, imports, or code execution.

    Args:
        expression: Mathematical expression string, e.g., '((42 + 58) * 2) / 4'.

    Returns:
        float: Computed result.

    Raises:
        CalculatorError: If syntax is invalid, unsupported nodes are present, or division by zero occurs.
    """
    clean_expr = expression.strip()
    if not clean_expr:
        raise CalculatorError("Empty expression cannot be evaluated.")

    try:
        parsed = ast.parse(clean_expr, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"Invalid arithmetic expression syntax: {exc}") from exc

    def _eval_node(node: ast.AST) -> Union[int, float]:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)

        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise CalculatorError(f"Unsupported constant type in math expression: {type(node.value).__name__}")

        elif isinstance(node, ast.BinOp):
            left_val = _eval_node(node.left)
            right_val = _eval_node(node.right)
            op_type = type(node.op)
            if op_type not in _SAFE_OPERATORS:
                raise CalculatorError(f"Unsupported arithmetic operator: {op_type.__name__}")

            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right_val == 0:
                raise CalculatorError("Division by zero is undefined.")

            try:
                op_func = _SAFE_OPERATORS[op_type]
                result = op_func(left_val, right_val)
                # Protect against astronomical power explosions
                if isinstance(result, complex):
                    raise CalculatorError("Complex numbers are not supported.")
                return result
            except OverflowError as exc:
                raise CalculatorError(f"Arithmetic overflow: {exc}") from exc

        elif isinstance(node, ast.UnaryOp):
            operand_val = _eval_node(node.operand)
            op_type = type(node.op)
            if op_type not in _SAFE_OPERATORS:
                raise CalculatorError(f"Unsupported unary operator: {op_type.__name__}")
            return _SAFE_OPERATORS[op_type](operand_val)

        else:
            # Strictly reject all other AST node types (Call, Name, Attribute, Import, etc.)
            raise CalculatorError(f"Security: disallowed expression element '{type(node).__name__}'.")

    return float(_eval_node(parsed))


def calculate(operation: str, a: float, b: float) -> float:
    """Perform a standard arithmetic calculation.

    Args:
        operation: One of 'add', 'subtract', 'multiply', 'divide'.
        a: First operand.
        b: Second operand.

    Returns:
        float: Calculated result.

    Raises:
        CalculatorError: If the operation is unknown or invalid.
    """
    op = operation.strip().lower()
    if op in ("add", "+", "plus", "addition"):
        return add(a, b)
    elif op in ("subtract", "-", "minus", "subtraction"):
        return subtract(a, b)
    elif op in ("multiply", "*", "times", "multiplication"):
        return multiply(a, b)
    elif op in ("divide", "/", "div", "division"):
        return divide(a, b)
    else:
        raise CalculatorError(
            f"Unknown arithmetic operation '{operation}'. Supported operations: add, subtract, multiply, divide."
        )

