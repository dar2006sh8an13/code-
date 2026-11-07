"""Unit tests for tool registration, argument validation, safe calculator, and tool loop execution."""

from unittest.mock import MagicMock

import pytest

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
    ToolExecutor,
)
from codeagent.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    get_default_registry,
)


class TestCalculator:
    """Test suite for safe arithmetic evaluation."""

    def test_addition(self) -> None:
        """Verify addition of integers and floats."""
        assert add(2, 3) == 5.0
        assert add(-5, 10.5) == 5.5

    def test_subtraction(self) -> None:
        """Verify subtraction."""
        assert subtract(10, 4) == 6.0
        assert subtract(3, 5) == -2.0

    def test_multiplication(self) -> None:
        """Verify multiplication."""
        assert multiply(6, 7) == 42.0
        assert multiply(-3, 4) == -12.0

    def test_division(self) -> None:
        """Verify division and division by zero prevention."""
        assert divide(10, 2) == 5.0
        assert divide(7, 2) == 3.5

        with pytest.raises(CalculatorError, match="Division by zero"):
            divide(10, 0)

    def test_unified_calculate_function(self) -> None:
        """Verify calculate function with operation dispatching."""
        assert calculate("add", 10, 20) == 30.0
        assert calculate("subtract", 50, 25) == 25.0
        assert calculate("multiply", 4, 5) == 20.0
        assert calculate("divide", 100, 4) == 25.0

        with pytest.raises(CalculatorError, match="Unknown arithmetic operation"):
            calculate("exponentiate_unknown", 2, 3)

    def test_safe_ast_arithmetic_evaluation(self) -> None:
        """Verify safe expression evaluation without eval()."""
        assert safe_eval_arithmetic("42 + 58") == 100.0
        assert safe_eval_arithmetic("((10 + 5) * 2) / 3") == 10.0
        assert safe_eval_arithmetic("100 - 50 + 25") == 75.0
        assert safe_eval_arithmetic("-5 * 4") == -20.0

    def test_safe_ast_rejects_unsafe_code(self) -> None:
        """Verify AST evaluator rejects arbitrary Python code, function calls, and variables."""
        with pytest.raises(CalculatorError):
            safe_eval_arithmetic("__import__('os').system('dir')")

        with pytest.raises(CalculatorError):
            safe_eval_arithmetic("open('test.txt')")

        with pytest.raises(CalculatorError):
            safe_eval_arithmetic("x + 5")


class TestToolRegistryAndExecutor:
    """Test suite for tool registration, schema validation, and loop limits."""

    def test_default_registry_contains_calculator_tools(self) -> None:
        """Verify default tools are properly registered with valid schemas."""
        registry = get_default_registry()
        assert registry.get("add") is not None
        assert registry.get("subtract") is not None
        assert registry.get("multiply") is not None
        assert registry.get("divide") is not None
        assert registry.get("calculate") is not None
        assert registry.get("evaluate_expression") is not None

        add_schema = registry.get("add").to_ollama_format()
        assert add_schema["type"] == "function"
        assert add_schema["function"]["name"] == "add"

    def test_argument_validation(self) -> None:
        """Verify argument checking against schema."""
        executor = ToolExecutor()

        # Valid arguments
        is_valid, err = executor.validate_arguments("add", {"a": 10, "b": 20})
        assert is_valid is True
        assert err is None

        # Missing required parameter
        is_valid, err = executor.validate_arguments("add", {"a": 10})
        assert is_valid is False
        assert "Missing required parameter 'b'" in err

        # Invalid type
        is_valid, err = executor.validate_arguments("add", {"a": "not_a_number", "b": 20})
        assert is_valid is False
        assert "must be a number" in err

        # Unregistered tool
        is_valid, err = executor.validate_arguments("unknown_tool", {})
        assert is_valid is False

    def test_execute_tool_success_and_error(self) -> None:
        """Verify tool execution returns structured ToolExecutionResult."""
        executor = ToolExecutor()

        res_ok = executor.execute("add", {"a": 15, "b": 25})
        assert res_ok.success is True
        assert res_ok.result == 40.0
        assert res_ok.to_message_content() == "40.0"

        res_err = executor.execute("divide", {"a": 10, "b": 0})
        assert res_err.success is False
        assert "Division by zero" in res_err.error

    def test_tool_loop_max_iterations_ceiling(self) -> None:
        """Verify infinite tool call loops trigger MaxIterationsExceededError."""
        executor = ToolExecutor()

        # Mock an LLM that keeps returning a tool call infinitely
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "add"
        mock_tool_call.function.arguments = {"a": 1, "b": 1}

        mock_msg = MagicMock(content="", tool_calls=[mock_tool_call])
        mock_client = MagicMock()
        mock_client.chat.return_value = MagicMock(message=mock_msg)

        with pytest.raises(MaxIterationsExceededError):
            executor.run_tool_loop(
                client=mock_client,
                model="qwen3:latest",
                messages=[{"role": "user", "content": "loop forever"}],
                max_iterations=3,
            )

        assert mock_client.chat.call_count == 3

    def test_duplicate_tool_call_detected(self):
        registry = ToolRegistry()
        call_count = 0

        def dummy_tool(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        registry.register(
            ToolDefinition(
                name="dummy_tool",
                description="A test tool",
                parameters={"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]},
                handler=dummy_tool,
            )
        )
        executor = ToolExecutor(registry=registry)

        # Mock client returning the exact same tool call twice in a row, then finishing
        tc = MagicMock()
        tc.function.name = "dummy_tool"
        tc.function.arguments = {"x": 5}

        turn1 = MagicMock()
        turn1.message.content = ""
        turn1.message.tool_calls = [tc]

        turn2 = MagicMock()
        turn2.message.content = ""
        turn2.message.tool_calls = [tc]

        turn3 = MagicMock()
        turn3.message.content = "Finished!"
        turn3.message.tool_calls = []

        mock_client = MagicMock()
        mock_client.chat.side_effect = [turn1, turn2, turn3]

        final_text, msgs = executor.run_tool_loop(
            client=mock_client,
            model="qwen3:latest",
            messages=[{"role": "user", "content": "run dummy"}],
            max_iterations=5,
        )

        assert final_text == "Finished!"
        # Tool should only have actually been invoked once because second identical call was blocked
        assert call_count == 1
        # The tool message for the second call should note it was a duplicate
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        assert "already executed with identical arguments" in tool_msgs[1]["content"]

    def test_string_json_arguments_parsed(self):
        registry = get_default_registry()
        executor = ToolExecutor(registry=registry)

        valid, err = executor.validate_arguments("calculate", '{"operation": "add", "a": 10, "b": 20}')
        assert valid is True
        assert err is None

        res = executor.execute("calculate", '{"operation": "multiply", "a": 6, "b": 7}')
        assert res.success is True
        assert res.result == 42

    def test_create_directory_tool(self, tmp_path):
        from codeagent.filesystem.manager import FilesystemManager
        from codeagent.config.settings import Settings

        settings = Settings(workspace_boundary=str(tmp_path))
        fs_mgr = FilesystemManager(settings=settings, workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr)
        executor = ToolExecutor(registry=registry)

        res = executor.execute("create_directory", {"path": "sub_dir/nested"})
        assert res.success is True
        assert (tmp_path / "sub_dir" / "nested").is_dir()

    def test_on_status_lifecycle_phases(self):
        registry = get_default_registry()
        executor = ToolExecutor(registry=registry)

        tc = MagicMock()
        tc.function.name = "calculate"
        tc.function.arguments = {"operation": "add", "a": 1, "b": 2}

        turn1 = MagicMock()
        turn1.message.content = "Planning addition"
        turn1.message.tool_calls = [tc]

        turn2 = MagicMock()
        turn2.message.content = "Result is 3"
        turn2.message.tool_calls = []

        mock_client = MagicMock()
        mock_client.chat.side_effect = [turn1, turn2]

        phases_logged = []

        def on_status(phase, details):
            phases_logged.append(phase)

        executor.run_tool_loop(
            client=mock_client,
            model="qwen3:latest",
            messages=[{"role": "user", "content": "1 + 2"}],
            on_status=on_status,
        )

        assert "Planning" in phases_logged
        assert "Generating" in phases_logged
        assert "Tool selected" in phases_logged
        assert "Executing" in phases_logged
        assert "Execution successful" in phases_logged


