"""Python program runner executing scripts safely inside the workspace boundary."""

from pathlib import Path
import sys
import tempfile
from typing import Optional, Union

from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.process_manager import ProcessManager
from codeagent.filesystem.path_validator import PathValidator, WorkspaceSecurityError


class PythonRunnerError(Exception):
    """Base exception for Python script execution errors."""
    pass


class ScriptNotFoundError(PythonRunnerError):
    """Raised when the target Python script does not exist."""
    pass


class PythonRunner:
    """Executes Python scripts and code snippets using the active virtual environment."""

    def __init__(
        self,
        process_manager: Optional[ProcessManager] = None,
        path_validator: Optional[PathValidator] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        """Initialize PythonRunner.

        Args:
            process_manager: ProcessManager instance.
            path_validator: PathValidator instance.
            python_executable: Path to Python interpreter (defaults to current sys.executable).
        """
        self.process_manager = process_manager or ProcessManager()
        self.path_validator = path_validator or PathValidator()
        self.python_executable = python_executable or sys.executable

    def run_script(
        self,
        script_path: Union[str, Path],
        args: Optional[list[str]] = None,
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Run a Python script file safely within workspace bounds.

        Args:
            script_path: Target .py script within the workspace.
            args: Optional command line arguments passed to script.
            cwd: Working directory (defaults to script parent or workspace root).
            timeout: Maximum execution seconds.

        Returns:
            ExecutionResult: Process output, exit code, and runtime.

        Raises:
            ScriptNotFoundError: If script does not exist.
            WorkspaceSecurityError: If script is outside workspace.
        """
        resolved_script = self.path_validator.validate_and_resolve(
            script_path,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        if not resolved_script.is_file():
            raise ScriptNotFoundError(f"Target Python script '{resolved_script}' is not a regular file.")

        resolved_cwd = (
            self.path_validator.validate_and_resolve(cwd, allow_nonexistent=False)
            if cwd
            else resolved_script.parent
        )

        cmd_args = [self.python_executable, str(resolved_script)]
        if args:
            cmd_args.extend(str(a) for a in args)

        return self.process_manager.execute_sync(
            args=cmd_args,
            cwd=resolved_cwd,
            timeout=timeout,
        )

    def run_code_string(
        self,
        code_str: str,
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute a Python code string using the interpreter -c switch or temp script.

        Args:
            code_str: Python code to execute.
            cwd: Working directory (defaults to workspace root).
            timeout: Maximum execution seconds.

        Returns:
            ExecutionResult: Captured execution outcome.
        """
        resolved_cwd = (
            self.path_validator.validate_and_resolve(cwd, allow_nonexistent=False)
            if cwd
            else self.path_validator.workspace_root
        )

        # Write to temporary file in workspace to prevent shell escaping errors on Windows
        temp_dir = self.path_validator.workspace_root / ".codeagent" / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_script = temp_dir / "snippet_exec.py"
        try:
            temp_script.write_text(code_str, encoding="utf-8")
            cmd_args = [self.python_executable, str(temp_script)]
            return self.process_manager.execute_sync(
                args=cmd_args,
                cwd=resolved_cwd,
                timeout=timeout,
            )
        finally:
            if temp_script.exists():
                try:
                    temp_script.unlink()
                except Exception:
                    pass

