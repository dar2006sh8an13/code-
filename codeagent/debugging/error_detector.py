"""Error detector identifying Python exceptions, test assertion failures, and non-zero exit codes."""

from dataclasses import asdict
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from codeagent.debugging.traceback_parser import ParsedTraceback, TracebackParser
from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.test_runner import TestReport


class DetectedError(BaseModel):
    """Structured representation of a detected error or failure."""

    error_type: str
    error_message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    execution_id: Optional[str] = None
    exit_code: Optional[int] = None
    raw_traceback: Optional[str] = None
    parsed_traceback: Optional[ParsedTraceback] = None
    test_failure_info: Optional[Dict[str, Any]] = None
    is_fatal: bool = True

    def to_summary(self) -> str:
        """Format an informative one-line or short summary."""
        loc = f" in {self.file_path}:{self.line_number}" if self.file_path else ""
        return f"{self.error_type}: {self.error_message}{loc}"


class ErrorDetector:
    """Detects and extracts structured error information from execution outcomes."""

    KNOWN_PYTHON_EXCEPTIONS = {
        "SyntaxError",
        "IndentationError",
        "TabError",
        "ImportError",
        "ModuleNotFoundError",
        "NameError",
        "UnboundLocalError",
        "TypeError",
        "AttributeError",
        "IndexError",
        "KeyError",
        "ValueError",
        "FileNotFoundError",
        "PermissionError",
        "FileExistsError",
        "ZeroDivisionError",
        "AssertionError",
        "RuntimeError",
        "RecursionError",
        "NotImplementedError",
        "TimeoutError",
        "ConnectionError",
        "MemoryError",
        "StopIteration",
        "UnicodeDecodeError",
        "UnicodeEncodeError",
    }

    PYTEST_FAIL_PATTERN = re.compile(
        r"FAILED\s+(?P<test_path>[^:\s]+)(?:::(?P<test_func>[^\s]+))?\s*(?:-\s*(?P<reason>.*))?",
        re.MULTILINE,
    )

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        """Initialize ErrorDetector with workspace context."""
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.parser = TracebackParser(workspace_root=self.workspace_root)

    def detect_from_execution_result(
        self,
        result: ExecutionResult,
        execution_id: Optional[str] = None,
    ) -> Optional[DetectedError]:
        """Detect errors from a Phase 5 ExecutionResult."""
        combined_output = f"{result.stderr}\n{result.stdout}".strip()

        # If success and exit_code 0, no error
        if result.success and result.exit_code == 0:
            return None

        # Check for traceback in output
        parsed_tb = self.parser.parse(combined_output)
        if parsed_tb:
            primary = parsed_tb.primary_frame
            return DetectedError(
                error_type=parsed_tb.exception_type,
                error_message=parsed_tb.exception_message,
                file_path=primary.file_path if primary else None,
                line_number=primary.line_number if primary else None,
                execution_id=execution_id,
                exit_code=result.exit_code,
                raw_traceback=parsed_tb.raw_text,
                parsed_traceback=parsed_tb,
                is_fatal=True,
            )

        # Check for pytest failures
        test_info = self._extract_pytest_failure(combined_output)
        if test_info:
            return DetectedError(
                error_type="AssertionError",
                error_message=test_info.get("reason") or "Test assertion failure",
                file_path=test_info.get("file_path"),
                execution_id=execution_id,
                exit_code=result.exit_code,
                test_failure_info=test_info,
                raw_traceback=combined_output,
                is_fatal=True,
            )

        # Check non-zero exit code with generic stderr message
        if result.exit_code is not None and result.exit_code != 0:
            lines = [line.strip() for line in (result.stderr or result.stdout).split("\n") if line.strip()]
            error_msg = lines[-1] if lines else f"Process exited with non-zero status code {result.exit_code}"
            return DetectedError(
                error_type="ProcessExecutionError",
                error_message=error_msg,
                execution_id=execution_id,
                exit_code=result.exit_code,
                raw_traceback=combined_output,
                is_fatal=True,
            )

        return None

    def detect_from_test_report(
        self,
        report: TestReport,
        execution_id: Optional[str] = None,
    ) -> Optional[DetectedError]:
        """Detect errors from a Phase 5 TestReport."""
        if report.status == "PASSED" and report.failed == 0:
            return None

        combined_output = f"{report.stderr}\n{report.stdout}".strip()
        test_info = self._extract_pytest_failure(combined_output)
        parsed_tb = self.parser.parse(combined_output)

        # 1. Prefer parsed traceback if it captured frames
        if parsed_tb and parsed_tb.frames:
            primary = parsed_tb.primary_frame
            return DetectedError(
                error_type=parsed_tb.exception_type,
                error_message=parsed_tb.exception_message,
                file_path=primary.file_path if primary else (test_info.get("file_path") if test_info else None),
                line_number=primary.line_number if primary else None,
                execution_id=execution_id,
                exit_code=1 if report.failed > 0 else 0,
                raw_traceback=parsed_tb.raw_text,
                parsed_traceback=parsed_tb,
                test_failure_info=test_info or {"failed_count": report.failed, "framework": report.framework},
                is_fatal=True,
            )

        # 2. Extract pytest failure info if traceback frames were not extracted
        if test_info and test_info.get("reason"):
            reason = test_info["reason"]
            err_type = "AssertionError"
            err_msg = reason
            if ":" in reason:
                parts = reason.split(":", 1)
                first_word = parts[0].strip()
                if first_word in self.KNOWN_PYTHON_EXCEPTIONS or first_word.endswith("Error") or first_word.endswith("Exception"):
                    err_type = first_word
                    err_msg = parts[1].strip()

            return DetectedError(
                error_type=err_type,
                error_message=err_msg,
                file_path=test_info.get("file_path"),
                execution_id=execution_id,
                exit_code=1 if report.failed > 0 else 0,
                test_failure_info=test_info,
                raw_traceback=combined_output,
                parsed_traceback=parsed_tb,
                is_fatal=True,
            )

        # 3. Parsed traceback without frames
        if parsed_tb:
            return DetectedError(
                error_type=parsed_tb.exception_type,
                error_message=parsed_tb.exception_message,
                file_path=test_info.get("file_path") if test_info else None,
                line_number=None,
                execution_id=execution_id,
                exit_code=1 if report.failed > 0 else 0,
                raw_traceback=parsed_tb.raw_text,
                parsed_traceback=parsed_tb,
                test_failure_info=test_info or {"failed_count": report.failed, "framework": report.framework},
                is_fatal=True,
            )

        return DetectedError(
            error_type="TestFailure",
            error_message=f"{report.failed} test(s) failed out of {report.total}",
            file_path=test_info.get("file_path") if test_info else None,
            execution_id=execution_id,
            exit_code=1,
            raw_traceback=combined_output,
            test_failure_info=test_info or {"failed_count": report.failed, "framework": report.framework},
            is_fatal=True,
        )

    def detect_from_text(self, text: str, exit_code: Optional[int] = None) -> Optional[DetectedError]:
        """Detect errors from raw console or logging text."""
        if not text or not text.strip():
            return None

        parsed_tb = self.parser.parse(text)
        if parsed_tb:
            primary = parsed_tb.primary_frame
            return DetectedError(
                error_type=parsed_tb.exception_type,
                error_message=parsed_tb.exception_message,
                file_path=primary.file_path if primary else None,
                line_number=primary.line_number if primary else None,
                exit_code=exit_code,
                raw_traceback=parsed_tb.raw_text,
                parsed_traceback=parsed_tb,
                is_fatal=True,
            )

        test_info = self._extract_pytest_failure(text)
        if test_info:
            return DetectedError(
                error_type="AssertionError",
                error_message=test_info.get("reason") or "Test assertion failure",
                file_path=test_info.get("file_path"),
                exit_code=exit_code,
                test_failure_info=test_info,
                raw_traceback=text,
                is_fatal=True,
            )

        # Check for direct Exception: Message
        for exc_name in self.KNOWN_PYTHON_EXCEPTIONS:
            pattern = re.compile(rf"\b{exc_name}:\s*(?P<msg>[^\n]+)")
            match = pattern.search(text)
            if match:
                return DetectedError(
                    error_type=exc_name,
                    error_message=match.group("msg").strip(),
                    exit_code=exit_code,
                    raw_traceback=text,
                    is_fatal=True,
                )

        if exit_code and exit_code != 0:
            lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
            return DetectedError(
                error_type="RuntimeError",
                error_message=lines[-1] if lines else f"Exit code {exit_code}",
                exit_code=exit_code,
                raw_traceback=text,
                is_fatal=True,
            )

        return None

    def _extract_pytest_failure(self, output: str) -> Optional[Dict[str, Any]]:
        """Extract test failure details from pytest stdout."""
        match = self.PYTEST_FAIL_PATTERN.search(output)
        if not match:
            return None
        return {
            "file_path": match.group("test_path").strip(),
            "test_function": match.group("test_func"),
            "reason": (match.group("reason") or "").strip(),
        }
