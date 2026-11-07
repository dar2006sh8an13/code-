"""Unit tests for Git diff generation, staged/unstaged separation, secret scrubbing, and binary guards."""

from pathlib import Path
import subprocess
import pytest

from codeagent.git.diff_manager import DiffManager


@pytest.fixture
def repo_with_diffs(tmp_path: Path) -> tuple[Path, DiffManager]:
    """Create a temporary Git repo with base files and DiffManager."""
    repo = tmp_path / "diff_test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    file_a = repo / "file_a.txt"
    file_a.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
    file_b = repo / "file_b.py"
    file_b.write_text("def foo():\n    return 42\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=repo, check=True, capture_output=True)

    mgr = DiffManager(workspace_root=repo)
    return repo, mgr


def test_working_tree_diff(repo_with_diffs: tuple[Path, DiffManager]) -> None:
    """Verify unstaged working tree diff."""
    repo, mgr = repo_with_diffs
    (repo / "file_a.txt").write_text("line 1\nline 2 MODIFIED\nline 3\nline 4\n", encoding="utf-8")

    diff_res = mgr.get_diff(staged=False)
    assert diff_res.is_staged is False
    assert diff_res.total_files_changed == 1
    assert "file_a.txt" in diff_res.raw_diff
    assert "+line 2 MODIFIED" in diff_res.raw_diff
    assert "-line 2" in diff_res.raw_diff


def test_staged_diff(repo_with_diffs: tuple[Path, DiffManager]) -> None:
    """Verify staged diff (--cached)."""
    repo, mgr = repo_with_diffs
    (repo / "file_b.py").write_text("def foo():\n    return 100\n", encoding="utf-8")
    subprocess.run(["git", "add", "file_b.py"], cwd=repo, check=True, capture_output=True)

    # Working tree diff should be empty
    unstaged = mgr.get_diff(staged=False)
    assert unstaged.total_files_changed == 0

    # Staged diff should show the change
    staged = mgr.get_diff(staged=True)
    assert staged.is_staged is True
    assert staged.total_files_changed == 1
    assert "file_b.py" in staged.raw_diff
    assert "+    return 100" in staged.raw_diff


def test_file_specific_diff(repo_with_diffs: tuple[Path, DiffManager]) -> None:
    """Verify filtering diff by file path."""
    repo, mgr = repo_with_diffs
    (repo / "file_a.txt").write_text("line 1 changed\n", encoding="utf-8")
    (repo / "file_b.py").write_text("def foo(): return 999\n", encoding="utf-8")

    diff_a = mgr.get_diff(staged=False, file_path="file_a.txt")
    assert "file_a.txt" in diff_a.raw_diff
    assert "file_b.py" not in diff_a.raw_diff


def test_diff_secret_scrubbing(repo_with_diffs: tuple[Path, DiffManager]) -> None:
    """Verify that credentials and tokens are scrubbed from diff output."""
    repo, mgr = repo_with_diffs
    (repo / "file_a.txt").write_text(
        "API_KEY: sk-ant-api03-abcdef123456789012345678\nghp_123456789012345678901234567890123456\npassword: SuperSecretPassword123\n",
        encoding="utf-8",
    )

    diff_res = mgr.get_diff(staged=False)
    assert "SuperSecretPassword123" not in diff_res.raw_diff
    assert "[REDACTED" in diff_res.raw_diff


def test_binary_file_handling(repo_with_diffs: tuple[Path, DiffManager]) -> None:
    """Verify that binary file changes are safely rendered without corrupted bytes."""
    repo, mgr = repo_with_diffs
    bin_file = repo / "image.png"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x01\x02\x03\xff\xfe")
    subprocess.run(["git", "add", "image.png"], cwd=repo, check=True, capture_output=True)

    diff_res = mgr.get_diff(staged=True)
    found_bin = [f for f in diff_res.file_diffs if "image.png" in f.file_path]
    assert len(found_bin) == 1
    assert found_bin[0].is_binary is True
    assert "differs" in found_bin[0].diff_text

