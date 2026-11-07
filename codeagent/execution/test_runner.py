"""Test runner executing pytest and unittest suites with structured reporting."""

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Optional, Union

from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.process_manager import ProcessManager
from codeagent.filesystem.path_validator import PathValidator


@dataclass
class TestReport:
    """Structured report of executed test suite outcomes."""

    __test__ = False
    framework: str
    passed: int
    failed: int
    skipped: int
    total: int
    duration_seconds: float
    status: str  # "PASSED", "FAILED", "ERROR", "TIMEOUT"
    stdout: str
    stderr: str

    def to_summary(self) -> str:
        """Format an informative summary of test execution."""
        return (
            f"Test Framework: {self.framework}\n"
            f"Status:   {self.status}\n"
            f"Passed:   {self.passed}\n"
            f"Failed:   {self.failed}\n"
            f"Skipped:  {self.skipped}\n"
            f"Total:    {self.total}\n"
            f"Duration: {self.duration_seconds:.2f}s"
        )


class TestRunner:
    """Discovers, executes, and parses test suites using pytest or unittest."""

    __test__ = False

    def __init__(
        self,
        process_manager: Optional[ProcessManager] = None,
        path_validator: Optional[PathValidator] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        """Initialize TestRunner.

        Args:
            process_manager: ProcessManager instance.
            path_validator: PathValidator instance.
            python_executable: Active Python interpreter path.
        """
        self.process_manager = process_manager or ProcessManager()
        self.path_validator = path_validator or PathValidator()
        self.python_executable = python_executable or sys.executable

    def detect_framework(self) -> str:
        """Determine whether pytest or unittest should be used."""
        ws = self.path_validator.workspace_root
        # Check for pytest indicators
        if (ws / "pytest.ini").exists() or (ws / "pyproject.toml").exists():
            return "pytest"
        if (ws / "tests").exists() or list(ws.glob("test_*.py")):
            return "pytest"
        return "unittest"

    def find_test_files(self) -> list[str]:
        """Locate test files within the workspace."""
        ws = self.path_validator.workspace_root
        test_files: list[str] = []
        for p in ws.rglob("test_*.py"):
            # Skip virtual environments and hidden dirs
            if any(part in p.parts for part in [".venv", "venv", "__pycache__", ".git", ".codeagent"]):
                continue
            test_files.append(str(p.relative_to(ws)))
        return sorted(test_files)

    @staticmethod
    def _parse_pytest_output(output: str) -> tuple[int, int, int]:
        """Extract passed, failed, skipped counts from pytest summary lines."""
        passed = 0
        failed = 0
        skipped = 0

        # Match e.g. "5 passed, 2 failed, 1 skipped in 1.23s"
        pass_match = re.search(r"(\d+)\s+passed", output)
        if pass_match:
            passed = int(pass_match.group(1))

        fail_match = re.search(r"(\d+)\s+failed", output)
        if fail_match:
            failed = int(fail_match.group(1))

        error_match = re.search(r"(\d+)\s+error", output)
        if error_match:
            failed += int(error_match.group(1))

        skip_match = re.search(r"(\d+)\s+skipped", output)
        if skip_match:
            skipped = int(skip_match.group(1))

        return passed, failed, skipped

    @staticmethod
    def _parse_unittest_output(output: str) -> tuple[int, int, int]:
        """Extract passed, failed, skipped counts from unittest summary lines."""
        passed = 0
        failed = 0
        skipped = 0

        ran_match = re.search(r"Ran\s+(\d+)\s+test", output)
        total_ran = int(ran_match.group(1)) if ran_match else 0

        fail_match = re.search(r"failures=(\d+)", output)
        if fail_match:
            failed += int(fail_match.group(1))

        err_match = re.search(r"errors=(\d+)", output)
        if err_match:
            failed += int(err_match.group(1))

        skip_match = re.search(r"skipped=(\d+)", output)
        if skip_match:
            skipped = int(skip_match.group(1))

        passed = max(0, total_ran - failed - skipped)
        return passed, failed, skipped

    def run(
        self,
        framework: Optional[str] = None,
        test_path: Optional[str] = None,
        extra_args: Optional[list[str]] = None,
        timeout: Optional[float] = None,
    ) -> TestReport:
        """Run project tests and return structured metrics.

        Args:
            framework: "pytest" or "unittest" (auto-detected if None).
            test_path: Specific test file or directory path relative to workspace.
            extra_args: Additional command line flags.
            timeout: Maximum execution timeout in seconds.

        Returns:
            TestReport: Parsed test results and counts.
        """
        fw = (framework or self.detect_framework()).lower()
        ws = self.path_validator.workspace_root

        target_file_str = None
        if test_path:
            resolved_target = self.path_validator.validate_and_resolve(test_path, allow_nonexistent=False)
            target_file_str = str(resolved_target.relative_to(ws))

        cmd_args: list[str] = []

        if fw == "pytest":
            cmd_args = [self.python_executable, "-m", "pytest"]
            if target_file_str:
                cmd_args.append(target_file_str)
            if extra_args:
                cmd_args.extend(extra_args)
        else:
            fw = "unittest"
            cmd_args = [self.python_executable, "-m", "unittest"]
            if target_file_str:
                cmd_args.append(target_file_str)
            else:
                cmd_args.extend(["discover", "-s", "."])
            if extra_args:
                cmd_args.extend(extra_args)

        res = self.process_manager.execute_sync(
            args=cmd_args,
            cwd=ws,
            timeout=timeout,
        )

        combined_output = f"{res.stdout}\n{res.stderr}"

        if fw == "pytest":
            passed, failed, skipped = self._parse_pytest_output(combined_output)
        else:
            passed, failed, skipped = self._parse_unittest_output(combined_output)

        total = passed + failed + skipped

        if res.timed_out:
            status = "TIMEOUT"
        elif res.exit_code == 0:
            status = "PASSED"
        elif failed > 0:
            status = "FAILED"
        else:
            status = "ERROR"

        return TestReport(
            framework=fw,
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=total,
            duration_seconds=res.duration_seconds,
            status=status,
            stdout=res.stdout,
            stderr=res.stderr,
        )
