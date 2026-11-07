"""Unit tests for PythonRunner."""

from pathlib import Path
import pytest

from codeagent.execution.python_runner import PythonRunner, ScriptNotFoundError
from codeagent.filesystem.path_validator import PathValidator, WorkspaceSecurityError


class TestPythonRunner:
    """Test suite for safe Python script execution."""

    def test_run_script_success(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        runner = PythonRunner(path_validator=validator)

        script = tmp_path / "hello.py"
        script.write_text("import sys; print('arg:', sys.argv[1])", encoding="utf-8")

        res = runner.run_script("hello.py", args=["CodeAG"])
        assert res.success is True
        assert res.exit_code == 0
        assert "arg: CodeAG" in res.stdout

    def test_run_script_not_found(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        runner = PythonRunner(path_validator=validator)

        with pytest.raises(FileNotFoundError):
            runner.run_script("missing.py")

    def test_run_script_outside_workspace_rejected(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        outside_script = outside / "bad.py"
        outside_script.write_text("print('bad')", encoding="utf-8")

        validator = PathValidator(workspace_root=ws)
        runner = PythonRunner(path_validator=validator)

        with pytest.raises(WorkspaceSecurityError):
            runner.run_script(outside_script)

    def test_run_code_string_snippet(self, tmp_path: Path) -> None:
        validator = PathValidator(workspace_root=tmp_path)
        runner = PythonRunner(path_validator=validator)

        res = runner.run_code_string("x = 15; y = 25; print(x + y)")
        assert res.success is True
        assert "40" in res.stdout

