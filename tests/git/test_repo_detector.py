"""Unit tests for Git repository detection and workspace boundary validation."""

from pathlib import Path
import subprocess
import pytest

from codeagent.git.repo_detector import (
    GitExecutionError,
    GitNotInstalledError,
    GitRepoInfo,
    GitSecurityError,
    NotAGitRepositoryError,
    RepoDetector,
)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Initialize a clean temporary Git repository with an initial commit."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    init_file = repo / "README.md"
    init_file.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True)
    return repo


def test_git_available() -> None:
    """Verify that git executable is detected on PATH."""
    detector = RepoDetector()
    assert detector.check_git_available() is True
    version = detector.get_git_version()
    assert "git version" in version.lower()


def test_detect_repository_success(temp_git_repo: Path) -> None:
    """Verify detection of a valid Git repository."""
    detector = RepoDetector(workspace_root=temp_git_repo)
    info = detector.detect_repository(temp_git_repo)

    assert info.is_git_repo is True
    assert info.current_branch == "main"
    assert info.has_commits is True
    assert info.head_commit_hash is not None
    assert len(info.head_commit_hash) == 40
    assert info.is_clean is True
    assert info.is_detached_head is False


def test_detect_non_git_directory(tmp_path: Path) -> None:
    """Verify detection reports false when directory is not a Git repo."""
    non_repo = tmp_path / "plain_dir"
    non_repo.mkdir()

    detector = RepoDetector(workspace_root=non_repo)
    info = detector.detect_repository(non_repo)

    assert info.is_git_repo is False
    assert info.current_branch is None
    assert info.has_commits is False


def test_detect_empty_git_repo(tmp_path: Path) -> None:
    """Verify handling of a newly initialized Git repository with no commits."""
    empty_repo = tmp_path / "empty_repo"
    empty_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=empty_repo, check=True, capture_output=True)

    detector = RepoDetector(workspace_root=empty_repo)
    info = detector.detect_repository(empty_repo)

    assert info.is_git_repo is True
    assert info.has_commits is False
    assert info.head_commit_hash is None


def test_workspace_boundary_enforcement(tmp_path: Path) -> None:
    """Verify that targeting directories outside the workspace raises GitSecurityError."""
    workspace = tmp_path / "allowed_workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "forbidden_outside"
    outside_dir.mkdir()

    detector = RepoDetector(workspace_root=workspace)
    with pytest.raises(GitSecurityError):
        detector.detect_repository(outside_dir)

