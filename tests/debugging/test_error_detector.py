"""Unit tests for error detection from execution results, test reports, and raw text."""

from pathlib import Path
import pytest

from codeagent.debugging.error_detector import DetectedError, ErrorDetector
from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.test_runner import TestReport


class TestErrorDetector:
    """Test suite for ErrorDetector."""

    def test_detect_syntax_error(self, tmp_path: Path) -> None:
        """Detect SyntaxError from terminal stderr."""
        detector = ErrorDetector(workspace_root=tmp_path)
        raw_text = """  File "app.py", line 5
    if True
          ^
SyntaxError: expected ':'
"""
        err = detector.detect_from_text(raw_text)
        assert err is not None
        assert err.error_type == "SyntaxError"
        assert "expected ':'" in err.error_message
        assert err.line_number == 5
        assert err.file_path == "app.py"

    def test_detect_import_and_module_not_found_error(self, tmp_path: Path) -> None:
        """Detect ModuleNotFoundError and ImportError."""
        detector = ErrorDetector(workspace_root=tmp_path)
        err = detector.detect_from_text("ModuleNotFoundError: No module named 'flask'")
        assert err is not None
        assert err.error_type == "ModuleNotFoundError"
        assert "flask" in err.error_message

    def test_detect_runtime_exceptions(self, tmp_path: Path) -> None:
        """Detect standard runtime errors like ZeroDivisionError and KeyError."""
        detector = ErrorDetector(workspace_root=tmp_path)
        tb = """Traceback (most recent call last):
  File "math_ops.py", line 10, in div
    return a / b
ZeroDivisionError: division by zero
"""
        err = detector.detect_from_text(tb)
        assert err is not None
        assert err.error_type == "ZeroDivisionError"
        assert err.error_message == "division by zero"
        assert err.line_number == 10

    def test_detect_from_failed_execution_result(self, tmp_path: Path) -> None:
        """Extract DetectedError from Phase 5 ExecutionResult."""
        detector = ErrorDetector(workspace_root=tmp_path)
        exec_res = ExecutionResult(
            command="python main.py",
            exit_code=1,
            stdout="",
            stderr="Traceback (most recent call last):\n  File \"main.py\", line 20, in <module>\n    raise ValueError('Bad value')\nValueError: Bad value\n",
            duration_seconds=0.5,
            timed_out=False,
            working_directory=str(tmp_path),
        )
        err = detector.detect_from_execution_result(exec_res, execution_id="exec_123")
        assert err is not None
        assert err.error_type == "ValueError"
        assert err.error_message == "Bad value"
        assert err.exit_code == 1
        assert err.execution_id == "exec_123"

    def test_detect_from_failed_test_report(self, tmp_path: Path) -> None:
        """Extract DetectedError from Phase 5 TestReport."""
        detector = ErrorDetector(workspace_root=tmp_path)
        report = TestReport(
            framework="pytest",
            passed=5,
            failed=1,
            skipped=0,
            total=6,
            duration_seconds=1.2,
            status="FAILED",
            stdout="FAILED tests/test_calc.py::test_addition - AssertionError: assert 4 == 5",
            stderr="",
        )
        err = detector.detect_from_test_report(report)
        assert err is not None
        assert err.error_type == "AssertionError"
        assert "assert 4 == 5" in err.error_message
        assert err.test_failure_info is not None
        assert err.test_failure_info["file_path"] == "tests/test_calc.py"

    def test_successful_execution_returns_none(self, tmp_path: Path) -> None:
        """Verify clean execution produces no detected error."""
        detector = ErrorDetector(workspace_root=tmp_path)
        exec_res = ExecutionResult(
            command="python main.py",
            exit_code=0,
            stdout="Hello World",
            stderr="",
            duration_seconds=0.1,
            timed_out=False,
            working_directory=str(tmp_path),
        )
        err = detector.detect_from_execution_result(exec_res)
        assert err is None
