"""Unit tests for CoderAgent, guarded writes, backups, syntax checks, and protected paths."""

import pytest
from codeagent.agents.coder_agent import CoderAgent, CoderInput, CoderOutput
from codeagent.config.settings import Settings
from codeagent.filesystem.manager import FilesystemManager
from codeagent.safety.backup_manager import SafetyBackupManager
from codeagent.safety.protected_paths import ProtectedPathsManager


def test_coder_creates_and_validates_python_file(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    fs_mgr = FilesystemManager(settings=settings)
    coder = CoderAgent(filesystem_manager=fs_mgr, settings=settings)

    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    inp = CoderInput(
        task_id="task_1",
        task_name="Implement add function",
        description="Write math function in math_module.py",
        files_to_create={"math_module.py": code},
    )

    out = coder.execute(inp)
    assert out.success is True
    assert "math_module.py" in out.files_created
    assert (tmp_path / "math_module.py").read_text(encoding="utf-8") == code


def test_coder_detects_python_syntax_error(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    fs_mgr = FilesystemManager(settings=settings)
    coder = CoderAgent(filesystem_manager=fs_mgr, settings=settings)

    broken_code = "def broken(:\n    pass\n"
    inp = CoderInput(
        task_id="task_syntax",
        task_name="Broken code",
        description="Write invalid syntax",
        files_to_create={"broken.py": broken_code},
    )

    out = coder.execute(inp)
    assert out.success is False
    assert "Syntax error" in out.changes_summary
    assert out.verification_status == "FAILED"


def test_coder_blocks_protected_files(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    fs_mgr = FilesystemManager(settings=settings)
    protected_paths = ProtectedPathsManager(workspace_root=tmp_path)
    coder = CoderAgent(
        filesystem_manager=fs_mgr,
        protected_paths_manager=protected_paths,
        settings=settings,
    )

    inp = CoderInput(
        task_id="task_sec",
        task_name="Modify environment",
        description="Tamper with .env",
        files_to_create={".env": "SECRET=leak"},
    )

    out = coder.execute(inp)
    assert out.success is False
    assert "Security violation" in out.changes_summary
    assert not (tmp_path / ".env").exists()

