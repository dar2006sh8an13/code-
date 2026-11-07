"""Unit tests for OutputCapture buffer limits and formatting."""

from pathlib import Path
import pytest

from codeagent.execution.output_capture import ExecutionResult, OutputCapture


class TestOutputCapture:
    """Test suite for process output capturing and size limits."""

    def test_output_capture_decoding_and_success(self) -> None:
        capture = OutputCapture(max_size_mb=1)
        res = capture.format_result(
            command="python -v",
            stdout_raw=b"Python 3.12\n",
            stderr_raw=b"",
            exit_code=0,
            duration=0.15,
            timed_out=False,
            cwd="/workspace",
        )

        assert res.success is True
        assert res.stdout == "Python 3.12\n"
        assert res.exit_code == 0
        assert res.timed_out is False
        assert res.truncated is False

    def test_output_truncation_when_exceeding_limit(self) -> None:
        capture = OutputCapture(max_size_mb=1)  # 1 MB limit
        large_bytes = b"A" * (2 * 1024 * 1024)  # 2 MB

        res = capture.format_result(
            command="cat large.txt",
            stdout_raw=large_bytes,
            stderr_raw=b"",
            exit_code=0,
            duration=0.5,
            timed_out=False,
            cwd="/workspace",
        )

        assert res.truncated is True
        assert "[Output truncated" in res.stdout

