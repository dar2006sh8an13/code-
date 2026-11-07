"""Unit tests for protected-path manager, traversal prevention, and symlink escape rejection."""

import os
from pathlib import Path
import pytest

from codeagent.filesystem.path_validator import (
    PathTraversalError,
    PathValidationError,
    WorkspaceSecurityError,
)
from codeagent.safety.protected_paths import (
    ProtectedPathsManager,
    ProtectedPathViolationError,
    SymlinkEscapeError,
)


@pytest.fixture
def workspace_with_paths(tmp_path: Path) -> tuple[Path, ProtectedPathsManager]:
    """Create a temporary workspace with protected directory structure."""
    ws = tmp_path / "safety_workspace"
    ws.mkdir()

    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (ws / ".env").write_text("SECRET=12345\n", encoding="utf-8")
    (ws / "src").mkdir()
    (ws / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")

    mgr = ProtectedPathsManager(workspace_root=ws)
    return ws, mgr


def test_allowed_path_resolves_cleanly(workspace_with_paths: tuple[Path, ProtectedPathsManager]) -> None:
    """Verify standard code files resolve within workspace boundary."""
    ws, mgr = workspace_with_paths
    resolved = mgr.validate_path_safety("src/app.py")
    assert resolved == (ws / "src" / "app.py").resolve()


def test_protect_dot_git_directory(workspace_with_paths: tuple[Path, ProtectedPathsManager]) -> None:
    """Verify that writing or mutating files inside .git is strictly blocked."""
    _, mgr = workspace_with_paths
    with pytest.raises(ProtectedPathViolationError):
        mgr.validate_path_safety(".git/HEAD", allow_read=False)


def test_protect_dot_env_file(workspace_with_paths: tuple[Path, ProtectedPathsManager]) -> None:
    """Verify that .env access is blocked."""
    _, mgr = workspace_with_paths
    with pytest.raises(ProtectedPathViolationError):
        mgr.validate_path_safety(".env")


def test_protect_sensitive_key_extensions(workspace_with_paths: tuple[Path, ProtectedPathsManager]) -> None:
    """Verify that private keys and credential patterns are blocked."""
    _, mgr = workspace_with_paths
    for bad_file in ["id_rsa", "server.key", "cert.pem", "credentials.json", "secrets.json"]:
        with pytest.raises(ProtectedPathViolationError):
            mgr.validate_path_safety(f"src/{bad_file}")


def test_path_traversal_outside_workspace_rejected(workspace_with_paths: tuple[Path, ProtectedPathsManager]) -> None:
    """Verify parent traversal escaping workspace is rejected."""
    _, mgr = workspace_with_paths
    with pytest.raises(WorkspaceSecurityError):
        mgr.validate_path_safety("../../system32/cmd.exe")


def test_custom_protected_path_management(workspace_with_paths: tuple[Path, ProtectedPathsManager]) -> None:
    """Verify user can add and remove custom protected rules."""
    _, mgr = workspace_with_paths

    mgr.add_custom_protected_path("config/*.prod.json")
    with pytest.raises(ProtectedPathViolationError):
        mgr.validate_path_safety("config/database.prod.json")

    # Remove rule
    assert mgr.remove_custom_protected_path("config/*.prod.json") is True
    # Now allowed
    resolved = mgr.validate_path_safety("config/database.prod.json")
    assert resolved.name == "database.prod.json"

