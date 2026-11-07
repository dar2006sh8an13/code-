"""Controlled Windows terminal execution for CMD, PowerShell, and direct binary invocation."""

from pathlib import Path
from typing import Optional, Union

from codeagent.execution.command_validator import CommandValidator
from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.process_manager import ProcessManager


class TerminalExecutor:
    """Executes validated commands inside Windows CMD, PowerShell, or direct process invocations."""

    def __init__(
        self,
        process_manager: Optional[ProcessManager] = None,
        validator: Optional[CommandValidator] = None,
    ) -> None:
        """Initialize TerminalExecutor.

        Args:
            process_manager: ProcessManager instance for subprocess execution.
            validator: CommandValidator instance.
        """
        self.process_manager = process_manager or ProcessManager()
        self.validator = validator or CommandValidator()

    def execute(
        self,
        command_or_args: Union[str, list[str]],
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
        shell_type: str = "direct",
    ) -> ExecutionResult:
        """Execute a validated command safely.

        Args:
            command_or_args: Raw string or list of argument tokens.
            cwd: Working directory (defaults to workspace root).
            timeout: Maximum allowed execution time in seconds.
            shell_type: "direct" (subprocess argument array), "cmd", or "powershell".

        Returns:
            ExecutionResult: Captured execution outcome.

        Raises:
            CommandValidationError: On security or validation failure.
        """
        # Validate command and resolve cwd
        exe, args, resolved_cwd = self.validator.validate_command(
            command_or_args,
            cwd=cwd,
            allow_shell_chaining=(shell_type in ("cmd", "powershell")),
        )

        full_args: list[str] = []

        if shell_type == "cmd":
            cmd_str = command_or_args if isinstance(command_or_args, str) else " ".join(command_or_args)
            full_args = ["cmd.exe", "/c", cmd_str]
        elif shell_type == "powershell":
            ps_cmd = command_or_args if isinstance(command_or_args, str) else " ".join(command_or_args)
            full_args = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "RemoteSigned",
                "-Command",
                ps_cmd,
            ]
        else:
            # Direct binary invocation via argument array (preferred, no shell)
            full_args = [exe] + args

        return self.process_manager.execute_sync(
            args=full_args,
            cwd=resolved_cwd,
            timeout=timeout,
        )

