"""Unit tests for CommandValidator security checks."""

from pathlib import Path
import pytest

from codeagent.execution.command_validator import (
    CommandInjectionError,
    CommandSecurityError,
    CommandValidationError,
    CommandValidator,
    DangerousCommandError,
    DisallowedExecutableError,
)
from codeagent.filesystem.path_validator import PathValidator


class TestCommandValidator:
    """Test suite for CommandValidator security boundaries and allowlists."""

    def test_valid_allowed_command(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        exe, args, cwd = validator.validate_command("python script.py")
        assert exe == "python"
        assert args == ["script.py"]
        assert cwd == tmp_path.resolve()

    def test_disallowed_executable_rejected(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        with pytest.raises(DisallowedExecutableError):
            validator.validate_command("untrusted_binary.exe --flag")

    def test_dangerous_destructive_command_rejected(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        with pytest.raises(DangerousCommandError):
            validator.validate_command("format C:")
        with pytest.raises(DangerousCommandError):
            validator.validate_command("rmdir /s /q test")
        with pytest.raises(DangerousCommandError):
            validator.validate_command("del /s important.txt")

    def test_command_injection_rejected(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        with pytest.raises(CommandInjectionError):
            validator.validate_command("python app.py && format C:")
        with pytest.raises(CommandInjectionError):
            validator.validate_command("dir | net user")
        with pytest.raises(CommandInjectionError):
            validator.validate_command("echo hello; del secret.txt")

    def test_argument_traversal_outside_workspace_rejected(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        with pytest.raises(CommandSecurityError):
            validator.validate_command("python ../../evil.py")

    def test_working_directory_outside_workspace_rejected(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        ws.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        validator = CommandValidator(path_validator=PathValidator(workspace_root=ws))
        with pytest.raises(CommandSecurityError):
            validator.validate_working_directory(outside)

