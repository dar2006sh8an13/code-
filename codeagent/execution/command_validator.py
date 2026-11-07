"""Command security validator enforcing executable allowlists, denylists, and injection checks."""

import os
from pathlib import Path
import re
import shlex
from typing import Optional, Union

from codeagent.filesystem.path_validator import PathValidator, WorkspaceSecurityError


class CommandValidationError(Exception):
    """Base exception for command validation errors."""
    pass


class CommandSecurityError(CommandValidationError):
    """Raised when an execution violates workspace or security boundaries."""
    pass


class DisallowedExecutableError(CommandValidationError):
    """Raised when an executable is not permitted by policy."""
    pass


class DangerousCommandError(CommandValidationError):
    """Raised when a destructive or dangerous command pattern is detected."""
    pass


class CommandInjectionError(CommandValidationError):
    """Raised when shell injection operators or unauthorized chaining are detected."""
    pass


# Disallowed system and destructive commands on Windows / POSIX
DANGEROUS_COMMANDS = {
    # System destructive
    "format", "diskpart", "bcdedit", "reg", "shutdown", "reboot",
    # Privilege escalation
    "runas", "sudo", "su",
    # User / Credential tampering
    "net", "net1", "attrib", "takeown", "icacls", "cacls",
    # Dangerous shell actions
    "del /s", "del /f", "rmdir /s", "rm -rf", "rd /s",
    # Dangerous powershell
    "remove-item -recurse -force", "set-executionpolicy unrestricted",
}

# Dangerous tokens or patterns within arguments
DANGEROUS_ARG_PATTERNS = [
    r"\brmdir\s+/[sq]",
    r"\bdel\s+/[sfq]",
    r"\brd\s+/[sq]",
    r"\bformat\s+[a-z]:",
    r"\bStart-Process\s+.*-Verb\s+RunAs",
    r"\bSet-ExecutionPolicy\s+(Unrestricted|Bypass)",
    r"\bcurl\s+.*\|\s*(bash|sh|powershell|cmd)",
    r"\bwget\s+.*\|\s*(bash|sh|powershell|cmd)",
]

# Explicitly allowed CLI utility executables
ALLOWED_BASE_EXECUTABLES = {
    "python", "python3", "python.exe", "python3.exe",
    "pip", "pip3", "pip.exe", "pip3.exe",
    "pytest", "pytest.exe",
    "git", "git.exe",
    "node", "node.exe", "npm", "npm.cmd", "npx", "npx.cmd",
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "echo", "dir", "type", "where", "find", "findstr", "cat", "ls",
}

# Shell injection characters when shell=False argument parsing is expected
SHELL_INJECTION_TOKENS = {";", "&", "|", "`", "$("}


class CommandValidator:
    """Validates command executables, arguments, and working directories against security policies."""

    def __init__(
        self,
        path_validator: Optional[PathValidator] = None,
        workspace_only: bool = True,
        allowed_executables: Optional[set[str]] = None,
    ) -> None:
        """Initialize CommandValidator.

        Args:
            path_validator: PathValidator for workspace boundary verification.
            workspace_only: Whether working directories must be inside workspace.
            allowed_executables: Optional custom set of permitted executables.
        """
        self.path_validator = path_validator or PathValidator()
        self.workspace_only = workspace_only
        self.allowed_executables = set(allowed_executables or ALLOWED_BASE_EXECUTABLES)

    def validate_working_directory(self, cwd: Optional[Union[str, Path]]) -> Path:
        """Verify and resolve working directory inside approved workspace.

        Args:
            cwd: Desired working directory (defaults to workspace root).

        Returns:
            Path: Canonical absolute working directory.

        Raises:
            CommandSecurityError: If directory is outside workspace or invalid.
        """
        target_dir = cwd or self.path_validator.workspace_root
        try:
            resolved = self.path_validator.validate_and_resolve(
                target_dir,
                allow_nonexistent=False,
                check_sensitive=True,
            )
            if not resolved.is_dir():
                raise CommandSecurityError(f"Working directory '{resolved}' is not a directory.")
            return resolved
        except (WorkspaceSecurityError, FileNotFoundError) as exc:
            raise CommandSecurityError(f"Invalid working directory '{target_dir}': {exc}") from exc

    def validate_command(
        self,
        command_or_args: Union[str, list[str]],
        cwd: Optional[Union[str, Path]] = None,
        allow_shell_chaining: bool = False,
    ) -> tuple[str, list[str], Path]:
        """Validate command string or argument list.

        Args:
            command_or_args: Raw string (e.g. 'python app.py') or list (['python', 'app.py']).
            cwd: Working directory.
            allow_shell_chaining: If False, rejects shell chaining symbols (&, |, ;).

        Returns:
            tuple[str, list[str], Path]: (executable_name, argument_list, resolved_cwd)

        Raises:
            DisallowedExecutableError: If executable is not in the allowlist.
            DangerousCommandError: If command matches dangerous or destructive actions.
            CommandInjectionError: If unapproved chaining or injection tokens are present.
            CommandSecurityError: If working directory or arguments violate workspace rules.
        """
        resolved_cwd = self.validate_working_directory(cwd)

        # Parse command into tokens
        if isinstance(command_or_args, str):
            raw_command = command_or_args.strip()
            if not raw_command:
                raise CommandValidationError("Command string cannot be empty.")

            # Check injection characters if shell chaining is not permitted
            if not allow_shell_chaining:
                for token in SHELL_INJECTION_TOKENS:
                    if token in raw_command:
                        raise CommandInjectionError(
                            f"Disallowed command operator or injection token '{token}' in command: '{raw_command}'."
                        )

            try:
                tokens = shlex.split(raw_command, posix=False)
            except ValueError as exc:
                raise CommandValidationError(f"Malformed command syntax: {exc}") from exc
        else:
            tokens = [str(arg).strip() for arg in command_or_args if str(arg).strip()]
            raw_command = " ".join(tokens)

        if not tokens:
            raise CommandValidationError("Command contains no valid tokens.")

        executable_token = tokens[0]
        arg_tokens = tokens[1:]

        # Check raw command against dangerous command strings
        raw_cmd_lower = raw_command.lower()
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in raw_cmd_lower:
                raise DangerousCommandError(
                    f"Blocked destructive command pattern '{dangerous}'."
                )

        # Check regex patterns
        for pattern in DANGEROUS_ARG_PATTERNS:
            if re.search(pattern, raw_command, flags=re.IGNORECASE):
                raise DangerousCommandError(
                    f"Command matched dangerous security rule: '{pattern}'."
                )

        # Extract base executable name
        exe_path = Path(executable_token)
        exe_name = exe_path.name.lower()
        exe_stem = exe_path.stem.lower()

        # Check if executable is allowed
        is_allowed = (
            exe_name in self.allowed_executables
            or exe_stem in self.allowed_executables
            or (exe_path.is_absolute() and self.path_validator.is_inside_workspace(exe_path))
        )

        if not is_allowed:
            raise DisallowedExecutableError(
                f"Executable '{executable_token}' is not in the permitted executable allowlist."
            )

        # Check argument tokens for path traversal or sensitive file targets
        for arg in arg_tokens:
            if arg.startswith(("-", "/")):
                continue  # Flags are checked by dangerous patterns
            # If argument looks like a relative file path, check that it doesn't escape workspace
            if "/" in arg or "\\" in arg or ".." in arg:
                if not self.path_validator.is_inside_workspace(resolved_cwd / arg):
                    raise CommandSecurityError(
                        f"Command argument '{arg}' attempts to access path outside workspace."
                    )

        return executable_token, arg_tokens, resolved_cwd

