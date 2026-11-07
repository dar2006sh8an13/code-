"""Unit tests for RetestManager executing test suites and scripts for post-patch verification."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from codeagent.debugging.retest_manager import RetestManager
from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.test_runner import TestReport


class TestRetestManager:
    """Test suite for RetestManager."""

    def test_retest_suite_resolved(self, tmp_path: Path) -> None:
        """Verify retest correctly marks issue resolved when all tests pass."""
        mock_exec = MagicMock()
        mock_exec.run_tests.return_value = TestReport(
            framework="pytest",
            passed=4,
            failed=0,
            skipped=0,
            total=4,
            duration_seconds=0.8,
            status="PASSED",
            stdout="4 passed in 0.8s",
            stderr="",
        )

        retest_mgr = RetestManager(execution_manager=mock_exec, workspace_root=tmp_path)
        result = retest_mgr.retest(test_path="tests/test_math.py", previous_failed_count=1)

        assert result.is_resolved is True
        assert result.status == "PASSED"
        assert result.passed == 4
        assert result.new_failed == 0
        assert result.previous_failed == 1
        mock_exec.run_tests.assert_called_once_with(test_path="tests/test_math.py", timeout=60.0)

    def test_retest_suite_still_failing(self, tmp_path: Path) -> None:
        """Verify retest marks issue unresolved when tests continue failing."""
        mock_exec = MagicMock()
        mock_exec.run_tests.return_value = TestReport(
            framework="pytest",
            passed=3,
            failed=1,
            skipped=0,
            total=4,
            duration_seconds=0.9,
            status="FAILED",
            stdout="1 failed, 3 passed",
            stderr="AssertionError",
        )

        retest_mgr = RetestManager(execution_manager=mock_exec, workspace_root=tmp_path)
        result = retest_mgr.retest(test_path="tests/test_math.py", previous_failed_count=1)

        assert result.is_resolved is False
        assert result.status == "FAILED"
        assert result.new_failed == 1

    def test_retest_standalone_script(self, tmp_path: Path) -> None:
        """Verify retest for a standalone Python script file."""
        mock_exec = MagicMock()
        mock_exec.run_python.return_value = ExecutionResult(
            command="python main.py",
            exit_code=0,
            stdout="Success",
            stderr="",
            duration_seconds=0.2,
            timed_out=False,
            working_directory=str(tmp_path),
        )

        retest_mgr = RetestManager(execution_manager=mock_exec, workspace_root=tmp_path)
        result = retest_mgr.retest(script_path="main.py")

        assert result.is_resolved is True
        assert result.status == "PASSED"
        mock_exec.run_python.assert_called_once()
