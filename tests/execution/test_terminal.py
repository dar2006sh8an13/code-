"""Unit tests for TerminalExecutor."""

from pathlib import Path
import sys
import pytest

from codeagent.execution.command_validator import CommandValidator, DisallowedExecutableError
from codeagent.execution.process_manager import ProcessManager
from codeagent.execution.terminal import TerminalExecutor
from codeagent.filesystem.path_validator import PathValidator


class TestTerminalExecutor:
    """Test suite for controlled terminal commands."""

    def test_direct_execution_python(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        terminal = TerminalExecutor(validator=validator)

        res = terminal.execute(
            command_or_args=[sys.executable, "-c", "print('terminal direct')"],
            cwd=tmp_path,
        )

        assert res.success is True
        assert "terminal direct" in res.stdout

    def test_cmd_execution_echo(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        terminal = TerminalExecutor(validator=validator)

        res = terminal.execute(
            command_or_args="echo hello_cmd",
            cwd=tmp_path,
            shell_type="cmd",
        )

        assert res.success is True
        assert "hello_cmd" in res.stdout

    def test_disallowed_command_rejected_before_spawn(self, tmp_path: Path) -> None:
        validator = CommandValidator(path_validator=PathValidator(workspace_root=tmp_path))
        terminal = TerminalExecutor(validator=validator)

        with pytest.raises(DisallowedExecutableError):
            terminal.execute("unknown_malware_tool.exe", cwd=tmp_path)

