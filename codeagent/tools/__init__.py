"""Tool-calling package for CodeAgent."""

from codeagent.tools.calculator import (
    CalculatorError,
    add,
    calculate,
    divide,
    multiply,
    safe_eval_arithmetic,
    subtract,
)
from codeagent.tools.executor import (
    MaxIterationsExceededError,
    ToolExecutionError,
    ToolExecutionResult,
    ToolExecutor,
)
from codeagent.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    get_default_registry,
)

__all__ = [
    "ToolRegistry",
    "ToolDefinition",
    "ToolExecutor",
    "ToolExecutionResult",
    "ToolExecutionError",
    "MaxIterationsExceededError",
    "CalculatorError",
    "add",
    "subtract",
    "multiply",
    "divide",
    "calculate",
    "safe_eval_arithmetic",
    "get_default_registry",
]

