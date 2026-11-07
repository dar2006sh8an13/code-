"""Process manager governing lifecycle, timeouts, process-tree termination, and concurrency."""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Optional, Union
import uuid

from codeagent.config.settings import Settings, get_settings
from codeagent.execution.output_capture import ExecutionResult, OutputCapture


class ProcessLimitExceededError(Exception):
    """Raised when maximum concurrent processes ceiling is reached."""
    pass


@dataclass
class ProcessInfo:
    """Metadata describing a tracked active or recent process."""

    process_id: int
    execution_id: str
    command: str
    working_directory: str
    start_time: float
    status: str  # "running", "completed", "failed", "cancelled", "timeout"


class ProcessManager:
    """Creates, tracks, monitors, and terminates subprocesses safely."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        output_capture: Optional[OutputCapture] = None,
    ) -> None:
        """Initialize ProcessManager.

        Args:
            settings: Settings configuration instance.
            output_capture: OutputCapture instance.
        """
        self.settings = settings or get_settings()
        self.output_capture = output_capture or OutputCapture(max_size_mb=self.settings.max_output_size_mb)
        self._active_processes: dict[int, tuple[subprocess.Popen, ProcessInfo]] = {}
        self._lock = threading.Lock()

    def _cleanup_finished(self) -> None:
        """Prune terminated processes from tracking dictionary."""
        with self._lock:
            pids = list(self._active_processes.keys())
            for pid in pids:
                proc, info = self._active_processes[pid]
                if proc.poll() is not None:
                    del self._active_processes[pid]

    def list_active_processes(self) -> list[ProcessInfo]:
        """Return list of currently running processes."""
        self._cleanup_finished()
        with self._lock:
            return [info for _, info in self._active_processes.values()]

    @staticmethod
    def terminate_process_tree(pid: int) -> None:
        """Forcefully terminate a process and all its child processes on Windows or POSIX."""
        if sys.platform == "win32":
            # Use Windows taskkill with /T (tree) and /F (force)
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                pass
        else:
            try:
                os.kill(pid, 9)
            except Exception:
                pass

    def cancel_process(self, pid: int) -> bool:
        """Cancel a running process by its PID.

        Args:
            pid: Process ID to terminate.

        Returns:
            bool: True if process was found and cancelled, False otherwise.
        """
        with self._lock:
            if pid not in self._active_processes:
                return False
            proc, info = self._active_processes[pid]
            info.status = "cancelled"

        self.terminate_process_tree(pid)
        return True

    def execute_sync(
        self,
        args: list[str],
        cwd: Union[str, Path],
        timeout: Optional[float] = None,
        env: Optional[dict[str, str]] = None,
        execution_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a process synchronously with timeout, output capture, and tracking.

        Args:
            args: Command arguments vector (first item is executable).
            cwd: Working directory.
            timeout: Maximum execution seconds (defaults to settings.execution_timeout_seconds).
            env: Custom environment variables.
            execution_id: Unique identifier for tracking.

        Returns:
            ExecutionResult: Captured stdout, stderr, exit code, and runtime.

        Raises:
            ProcessLimitExceededError: If max concurrent processes ceiling is reached.
            FileNotFoundError: If executable does not exist.
        """
        self._cleanup_finished()

        with self._lock:
            if len(self._active_processes) >= self.settings.max_concurrent_processes:
                raise ProcessLimitExceededError(
                    f"Maximum concurrent process limit ({self.settings.max_concurrent_processes}) reached. "
                    "Wait for running tasks to finish or cancel an existing process."
                )

        exec_id = execution_id or uuid.uuid4().hex[:10]
        cmd_str = " ".join(args)
        time_limit = timeout if timeout is not None else self.settings.execution_timeout_seconds
        start_mono = time.monotonic()
        timed_out = False

        # Merge process environment ensuring UTF-8 encoding on Windows
        proc_env = dict(os.environ)
        if env:
            proc_env.update(env)
        proc_env["PYTHONIOENCODING"] = "utf-8"
        proc_env["PYTHONUNBUFFERED"] = "1"

        try:
            # Spawn process with pipes
            proc = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=proc_env,
                shell=False,
            )

            p_info = ProcessInfo(
                process_id=proc.pid,
                execution_id=exec_id,
                command=cmd_str,
                working_directory=str(cwd),
                start_time=time.time(),
                status="running",
            )

            with self._lock:
                self._active_processes[proc.pid] = (proc, p_info)

            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=time_limit)
            except subprocess.TimeoutExpired:
                timed_out = True
                p_info.status = "timeout"
                self.terminate_process_tree(proc.pid)
                stdout_bytes, stderr_bytes = proc.communicate()

            duration = time.monotonic() - start_mono
            exit_code = proc.returncode if not timed_out else -1

            if not timed_out:
                p_info.status = "completed" if exit_code == 0 else "failed"

            return self.output_capture.format_result(
                command=cmd_str,
                stdout_raw=stdout_bytes,
                stderr_raw=stderr_bytes,
                exit_code=exit_code,
                duration=duration,
                timed_out=timed_out,
                cwd=cwd,
                process_id=proc.pid,
                execution_id=exec_id,
            )

        finally:
            self._cleanup_finished()

