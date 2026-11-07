"""Unit tests for Git status parsing with porcelain format, spaces in filenames, and state classification."""

from pathlib import Path
import subprocess
import pytest

from codeagent.git.repo_detector import RepoDetector
from codeagent.git.status_manager import GitStatusReport, StatusManager


@pytest.fixture
def repo_with_changes(tmp_path: Path) -> tuple[Path, StatusManager]:
    """Create a temporary repository with clean initial commit and StatusManager."""
    repo = tmp_path / "status_test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    base = repo / "base.txt"
    base.write_text("initial base content\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit base"], cwd=repo, check=True, capture_output=True)

    mgr = StatusManager(workspace_root=repo)
    return repo, mgr


def test_status_clean_repo(repo_with_changes: tuple[Path, StatusManager]) -> None:
    """Verify clean repository status report."""
    repo, mgr = repo_with_changes
    report = mgr.get_status()

    assert report.is_clean is True
    assert report.branch == "main"
    assert len(report.all_files) == 0
    assert "clean" in report.to_summary()


def test_status_unstaged_and_untracked_files(repo_with_changes: tuple[Path, StatusManager]) -> None:
    """Verify detecting modified unstaged and untracked files."""
    repo, mgr = repo_with_changes

    # 1. Modify tracked file (unstaged)
    (repo / "base.txt").write_text("updated base content\n", encoding="utf-8")
    # 2. Add untracked file
    (repo / "new_untracked.py").write_text("print('hello')\n", encoding="utf-8")

    report = mgr.get_status()
    assert report.is_clean is False
    assert len(report.all_files) == 2
    assert len(report.unstaged_files) == 1
    assert report.unstaged_files[0].path == "base.txt"
    assert len(report.untracked_files) == 1
    assert report.untracked_files[0].path == "new_untracked.py"


def test_status_staged_files(repo_with_changes: tuple[Path, StatusManager]) -> None:
    """Verify detecting explicitly staged files."""
    repo, mgr = repo_with_changes

    staged_file = repo / "staged.txt"
    staged_file.write_text("staged contents\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=repo, check=True, capture_output=True)

    report = mgr.get_status()
    assert report.is_clean is False
    assert len(report.staged_files) == 1
    assert report.staged_files[0].path == "staged.txt"
    assert report.staged_files[0].is_staged is True


def test_status_filenames_with_spaces(repo_with_changes: tuple[Path, StatusManager]) -> None:
    """Verify handling of files with spaces in paths."""
    repo, mgr = repo_with_changes

    space_file = repo / "document with space and symbols!.txt"
    space_file.write_text("space content\n", encoding="utf-8")

    report = mgr.get_status()
    assert report.is_clean is False
    found = [f for f in report.untracked_files if f.path == "document with space and symbols!.txt"]
    assert len(found) == 1


def test_status_rich_table_rendering(repo_with_changes: tuple[Path, StatusManager]) -> None:
    """Verify Rich table output contains file change entries."""
    repo, mgr = repo_with_changes
    (repo / "sample.py").write_text("x = 1\n", encoding="utf-8")

    report = mgr.get_status()
    table = report.to_rich_table()
    assert table.title is not None
    assert "main" in table.title

