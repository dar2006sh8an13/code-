"""Unit and integration tests for AutonomousDebugger controller workflow."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from codeagent.config.settings import Settings
from codeagent.debugging.debugger import AutonomousDebugger
from codeagent.debugging.error_detector import DetectedError
from codeagent.debugging.fix_generator import FilePatch
from codeagent.debugging.regression_checker import RegressionStatus
from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.test_runner import TestReport


class TestAutonomousDebugger:
    """Test suite for AutonomousDebugger."""

    def test_e2e_successful_debugging_workflow(self, tmp_path: Path) -> None:
        """Full 16-step flow: detect error, inspect code, propose patch, approve, retest, and verify."""
        src_file = tmp_path / "app.py"
        src_file.write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")

        mock_exec = MagicMock()
        # Initial run fails with ZeroDivisionError, retest run passes
        mock_exec.run_python.side_effect = [
            ExecutionResult(
                command="python app.py",
                exit_code=1,
                stdout="",
                stderr="Traceback (most recent call last):\n  File \"app.py\", line 2, in divide\n    return a / b\nZeroDivisionError: division by zero\n",
                duration_seconds=0.1,
                timed_out=False,
                working_directory=str(tmp_path),
            ),
            ExecutionResult(
                command="python app.py",
                exit_code=0,
                stdout="OK",
                stderr="",
                duration_seconds=0.1,
                timed_out=False,
                working_directory=str(tmp_path),
            ),
        ]

        debugger = AutonomousDebugger(
            workspace_root=tmp_path,
            execution_manager=mock_exec,
            require_patch_approval=True,
        )

        report = debugger.debug_target(
            script_path="app.py",
            approval_callback=lambda patch: True,
            custom_replacement=("return a / b", "return a / b if b != 0 else 0"),
        )

        assert report.final_status == "FIXED_AND_VERIFIED"
        assert report.patch_applied is True
        assert len(report.backups_created) >= 1
        assert "if b != 0 else 0" in src_file.read_text(encoding="utf-8")

    def test_e2e_user_rejected_patch(self, tmp_path: Path) -> None:
        """Verify workflow stops cleanly and does not modify disk when user rejects patch."""
        src_file = tmp_path / "protected_app.py"
        orig_text = "def compute():\n    raise ValueError('Fail')\n"
        src_file.write_text(orig_text, encoding="utf-8")

        initial_err = DetectedError(
            error_type="ValueError",
            error_message="Fail",
            file_path="protected_app.py",
            line_number=2,
        )

        debugger = AutonomousDebugger(
            workspace_root=tmp_path,
            require_patch_approval=True,
        )

        report = debugger.debug_target(
            initial_error=initial_err,
            approval_callback=lambda patch: False,  # User says NO
            custom_replacement=("raise ValueError('Fail')", "return 42"),
        )

        assert report.patch_applied is False
        assert report.final_status == "UNRESOLVED"
        # File on disk was untouched
        assert src_file.read_text(encoding="utf-8") == orig_text

    def test_iteration_limit_enforced(self, tmp_path: Path) -> None:
        """Ensure debugger does not exceed MAX_DEBUG_ITERATIONS or loop infinitely."""
        src_file = tmp_path / "stubborn.py"
        src_file.write_text("x = 1\n", encoding="utf-8")

        initial_err = DetectedError(
            error_type="RuntimeError",
            error_message="Persistent bug",
            file_path="stubborn.py",
            line_number=1,
        )

        settings = Settings(
            MAX_DEBUG_ITERATIONS=2,
            MAX_FIX_ATTEMPTS=2,
        )

        mock_exec = MagicMock()
        # Retests always continue to fail
        mock_exec.run_tests.return_value = TestReport(
            framework="pytest",
            passed=0,
            failed=1,
            skipped=0,
            total=1,
            duration_seconds=0.1,
            status="FAILED",
            stdout="FAILED - RuntimeError: Persistent bug",
            stderr="",
        )

        debugger = AutonomousDebugger(
            workspace_root=tmp_path,
            settings=settings,
            execution_manager=mock_exec,
        )

        report = debugger.debug_target(
            test_path="stubborn.py",
            initial_error=initial_err,
            bypass_approval=True,
            custom_replacement=("x = 1", "x = 2"),
        )

        # Iterations must not exceed ceiling
        assert report.iterations_count <= 2
        assert report.final_status != "FIXED_AND_VERIFIED"

    def test_rollback_session_restores_pre_patch_state(self, tmp_path: Path) -> None:
        """Verify rollback_session restores all files to pre-debugging state."""
        src_file = tmp_path / "rollback_me.py"
        orig_content = "def sample():\n    return 'original'\n"
        src_file.write_text(orig_content, encoding="utf-8")

        mock_exec = MagicMock()
        mock_exec.run_python.return_value = ExecutionResult(
            command="python rollback_me.py",
            exit_code=0,
            stdout="OK",
            stderr="",
            duration_seconds=0.1,
            timed_out=False,
            working_directory=str(tmp_path),
        )

        debugger = AutonomousDebugger(
            workspace_root=tmp_path,
            execution_manager=mock_exec,
        )

        report = debugger.debug_target(
            script_path="rollback_me.py",
            initial_error=DetectedError(error_type="ZeroDivisionError", error_message="error", file_path="rollback_me.py", line_number=2),
            bypass_approval=True,
            custom_replacement=("return 'original'", "return 'patched'"),
        )

        assert "patched" in src_file.read_text(encoding="utf-8")

        # Roll back session
        restored_count = debugger.rollback_session(report)
        assert restored_count == 1
        assert src_file.read_text(encoding="utf-8") == orig_content
