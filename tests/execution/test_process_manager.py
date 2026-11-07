"""Unit tests for ProcessManager process spawning, timeouts, and cancellation."""

from pathlib import Path
import sys
import pytest

from codeagent.config.settings import Settings
from codeagent.execution.process_manager import ProcessLimitExceededError, ProcessManager


class TestProcessManager:
    """Test suite for ProcessManager execution and timeout enforcement."""

    def test_sync_execution_success(self, tmp_path: Path) -> None:
        mgr = ProcessManager()
        res = mgr.execute_sync(
            args=[sys.executable, "-c", "print('hello from process')"],
            cwd=tmp_path,
            timeout=10,
        )

        assert res.success is True
        assert res.exit_code == 0
        assert "hello from process" in res.stdout

    def test_sync_execution_failure_exit_code(self, tmp_path: Path) -> None:
        mgr = ProcessManager()
        res = mgr.execute_sync(
            args=[sys.executable, "-c", "import sys; sys.exit(42)"],
            cwd=tmp_path,
            timeout=10,
        )

        assert res.success is False
        assert res.exit_code == 42

    def test_sync_execution_timeout(self, tmp_path: Path) -> None:
        mgr = ProcessManager()
        # Run a script that sleeps 5 seconds with a 0.5s timeout
        res = mgr.execute_sync(
            args=[sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            timeout=0.5,
        )

        assert res.timed_out is True
        assert res.success is False

    def test_concurrency_ceiling_enforced(self, tmp_path: Path) -> None:
        settings = Settings(_env_file=None, max_concurrent_processes=1)
        mgr = ProcessManager(settings=settings)

        # Fake an active process in the dictionary
        from unittest.mock import MagicMock
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None  # Still running
        fake_info = MagicMock()

        mgr._active_processes[99999] = (fake_proc, fake_info)

        with pytest.raises(ProcessLimitExceededError):
            mgr.execute_sync(
                args=[sys.executable, "-c", "print(1)"],
                cwd=tmp_path,
            )

