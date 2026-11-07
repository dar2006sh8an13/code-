"""Output capture engine with size ceilings, secret redaction, and structured reporting."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Union

from codeagent.execution.audit_logger import redact_secrets_text


@dataclass
class ExecutionResult:
    """Structured result of a completed or failed process execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    working_directory: str
    truncated: bool = False
    process_id: Optional[int] = None
    execution_id: Optional[str] = None

    @property
    def success(self) -> bool:
        """True if process exited with code 0 and did not time out."""
        return self.exit_code == 0 and not self.timed_out

    def to_summary(self) -> str:
        """Format an informative terminal summary of the execution outcome."""
        status_label = "TIMEOUT" if self.timed_out else ("SUCCESS" if self.success else f"FAILED (exit {self.exit_code})")
        trunc_note = " [Truncated]" if self.truncated else ""
        return (
            f"Command: {self.command}\n"
            f"Status: {status_label} | Duration: {self.duration_seconds:.2f}s | CWD: {self.working_directory}{trunc_note}"
        )


class OutputCapture:
    """Buffers, truncates, sanitizes, and structures standard output and error streams."""

    def __init__(self, max_size_mb: int = 5) -> None:
        """Initialize OutputCapture with byte limit.

        Args:
            max_size_mb: Maximum output stream size in megabytes before truncation.
        """
        self.max_bytes = max_size_mb * 1024 * 1024

    def format_result(
        self,
        command: str,
        stdout_raw: Union[str, bytes],
        stderr_raw: Union[str, bytes],
        exit_code: int,
        duration: float,
        timed_out: bool,
        cwd: Union[str, Path],
        process_id: Optional[int] = None,
        execution_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Sanitize and construct an ExecutionResult.

        Args:
            command: Executed command representation.
            stdout_raw: Raw stdout bytes or string.
            stderr_raw: Raw stderr bytes or string.
            exit_code: Process returncode.
            duration: Run duration in seconds.
            timed_out: Whether execution timed out.
            cwd: Working directory of execution.
            process_id: OS process PID if available.
            execution_id: Unique execution identifier.

        Returns:
            ExecutionResult: Structured and sanitized output record.
        """
        # Decode bytes if needed
        if isinstance(stdout_raw, bytes):
            stdout_text = stdout_raw.decode("utf-8", errors="replace")
        else:
            stdout_text = str(stdout_raw)

        if isinstance(stderr_raw, bytes):
            stderr_text = stderr_raw.decode("utf-8", errors="replace")
        else:
            stderr_text = str(stderr_raw)

        truncated = False

        # Apply byte limit truncation to stdout
        if len(stdout_text.encode("utf-8")) > self.max_bytes:
            truncated = True
            keep_chars = self.max_bytes // 2
            stdout_text = (
                stdout_text[:keep_chars]
                + f"\n\n... [Output truncated at {self.max_bytes // (1024 * 1024)} MB limit] ...\n"
            )

        # Apply byte limit truncation to stderr
        if len(stderr_text.encode("utf-8")) > self.max_bytes:
            truncated = True
            keep_chars = self.max_bytes // 2
            stderr_text = (
                stderr_text[:keep_chars]
                + f"\n\n... [Stderr truncated at {self.max_bytes // (1024 * 1024)} MB limit] ...\n"
            )

        # Redact credentials and tokens
        stdout_clean = redact_secrets_text(stdout_text)
        stderr_clean = redact_secrets_text(stderr_text)
        command_clean = redact_secrets_text(command)

        return ExecutionResult(
            command=command_clean,
            exit_code=exit_code,
            stdout=stdout_clean,
            stderr=stderr_clean,
            duration_seconds=duration,
            timed_out=timed_out,
            working_directory=str(cwd),
            truncated=truncated,
            process_id=process_id,
            execution_id=execution_id,
        )

