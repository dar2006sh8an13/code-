"""Retest manager executing verification runs and comparing before-and-after results."""

from pathlib import Path
from typing import List, Optional, Union
from pydantic import BaseModel, Field

from codeagent.execution.manager import ExecutionManager
from codeagent.execution.test_runner import TestReport, TestRunner


class RetestResult(BaseModel):
    """Structured report of retesting outcome after patch application."""

    test_target: str
    framework: str = "pytest"
    previous_failed: int = 1
    new_failed: int = 0
    passed: int = 0
    total: int = 0
    is_resolved: bool = False
    status: str = "PASSED"  # "PASSED", "FAILED", "ERROR"
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    def to_summary(self) -> str:
        """Format an informative summary of retest results."""
        res_str = "RESOLVED" if self.is_resolved else "UNRESOLVED"
        return (
            f"Retest Status: [{res_str}] ({self.status})\n"
            f"Target:        {self.test_target}\n"
            f"Passed:        {self.passed} / {self.total}\n"
            f"Failed:        {self.new_failed} (previously {self.previous_failed})\n"
            f"Duration:      {self.duration_seconds:.2f}s"
        )


class RetestManager:
    """Coordinates re-running previously failing tests and regression verification."""

    def __init__(
        self,
        execution_manager: Optional[ExecutionManager] = None,
        workspace_root: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize RetestManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.execution_manager = execution_manager or ExecutionManager(workspace_root=self.workspace_root)

    def retest(
        self,
        test_path: Optional[str] = None,
        script_path: Optional[str] = None,
        previous_failed_count: int = 1,
        timeout: float = 60.0,
    ) -> RetestResult:
        """Rerun a test suite or script and evaluate resolution status."""
        if test_path:
            return self._retest_suite(
                test_path=test_path,
                previous_failed=previous_failed_count,
                timeout=timeout,
            )
        elif script_path:
            return self._retest_script(
                script_path=script_path,
                timeout=timeout,
            )
        else:
            # Default: run all tests discovered in workspace
            return self._retest_suite(
                test_path=None,
                previous_failed=previous_failed_count,
                timeout=timeout,
            )

    def _retest_suite(
        self,
        test_path: Optional[str],
        previous_failed: int,
        timeout: float,
    ) -> RetestResult:
        """Rerun pytest/unittest suite."""
        report: TestReport = self.execution_manager.run_tests(
            test_path=test_path,
            timeout=timeout,
        )

        is_resolved = (report.status == "PASSED" and report.failed == 0)

        return RetestResult(
            test_target=test_path or "all project tests",
            framework=report.framework,
            previous_failed=previous_failed,
            new_failed=report.failed,
            passed=report.passed,
            total=report.total,
            is_resolved=is_resolved,
            status=report.status,
            stdout=report.stdout,
            stderr=report.stderr,
            duration_seconds=report.duration_seconds,
        )

    def _retest_script(
        self,
        script_path: str,
        timeout: float,
    ) -> RetestResult:
        """Rerun a standalone Python script."""
        exec_res = self.execution_manager.run_python(
            script_path=script_path,
            timeout=timeout,
            approved=True,
        )

        is_resolved = exec_res.success and exec_res.exit_code == 0

        return RetestResult(
            test_target=script_path,
            framework="python",
            previous_failed=1,
            new_failed=0 if is_resolved else 1,
            passed=1 if is_resolved else 0,
            total=1,
            is_resolved=is_resolved,
            status="PASSED" if is_resolved else "FAILED",
            stdout=exec_res.stdout,
            stderr=exec_res.stderr,
            duration_seconds=exec_res.duration_seconds,
        )

