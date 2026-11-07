"""Unit tests for TestRunner."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.test_runner import TestReport, TestRunner
from codeagent.filesystem.path_validator import PathValidator


class TestTestRunner:
    """Test suite for automated test execution and parsing."""

    def test_parse_pytest_output(self) -> None:
        raw = "=== 12 passed, 2 failed, 1 skipped in 1.45s ==="
        passed, failed, skipped = TestRunner._parse_pytest_output(raw)
        assert passed == 12
        assert failed == 2
        assert skipped == 1

    def test_parse_unittest_output(self) -> None:
        raw = "Ran 15 tests in 0.050s\nFAILED (failures=3, errors=1)"
        passed, failed, skipped = TestRunner._parse_unittest_output(raw)
        assert failed == 4
        assert passed == 11
        assert skipped == 0

    def test_run_tests_success_reporting(self, tmp_path: Path) -> None:
        mock_proc_mgr = MagicMock()
        mock_proc_mgr.execute_sync.return_value = ExecutionResult(
            command="python -m pytest",
            exit_code=0,
            stdout="=== 5 passed in 0.20s ===",
            stderr="",
            duration_seconds=0.20,
            timed_out=False,
            working_directory=str(tmp_path),
        )

        runner = TestRunner(
            process_manager=mock_proc_mgr,
            path_validator=PathValidator(workspace_root=tmp_path),
        )

        report = runner.run(framework="pytest")
        assert report.framework == "pytest"
        assert report.status == "PASSED"
        assert report.passed == 5
        assert report.failed == 0
        assert report.total == 5

    def test_run_tests_failure_reporting(self, tmp_path: Path) -> None:
        mock_proc_mgr = MagicMock()
        mock_proc_mgr.execute_sync.return_value = ExecutionResult(
            command="python -m pytest",
            exit_code=1,
            stdout="=== 4 passed, 2 failed in 0.35s ===",
            stderr="",
            duration_seconds=0.35,
            timed_out=False,
            working_directory=str(tmp_path),
        )

        runner = TestRunner(
            process_manager=mock_proc_mgr,
            path_validator=PathValidator(workspace_root=tmp_path),
        )

        report = runner.run(framework="pytest")
        assert report.status == "FAILED"
        assert report.passed == 4
        assert report.failed == 2
        assert report.total == 6

