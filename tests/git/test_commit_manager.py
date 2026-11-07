"""Unit tests for Git commit workflow, explicit staging, pre-commit secret scanning, and approval gates."""

from pathlib import Path
import subprocess
import pytest

from codeagent.git.commit_manager import (
    CommitManager,
    CommitNotApprovedError,
    CommitValidationError,
    SecretDetectedInCommitError,
)


@pytest.fixture
def repo_for_commits(tmp_path: Path) -> tuple[Path, CommitManager]:
    """Create a temporary Git repository with an initial commit."""
    repo = tmp_path / "commit_test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    base = repo / "README.md"
    base.write_text("# Initial Project\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True)

    mgr = CommitManager(workspace_root=repo)
    return repo, mgr


def test_reject_wildcard_staging(repo_for_commits: tuple[Path, CommitManager]) -> None:
    """Verify that attempting to stage entire tree or wildcards is strictly refused."""
    repo, mgr = repo_for_commits
    (repo / "new.txt").write_text("content\n", encoding="utf-8")

    for bad_arg in [".", "-A", "--all", "*"]:
        with pytest.raises(CommitValidationError) as exc:
            mgr.stage_explicit_files([bad_arg])
        assert "explicit file paths" in str(exc.value).lower()


def test_commit_changes_success(repo_for_commits: tuple[Path, CommitManager]) -> None:
    """Verify end-to-end controlled commit with hash verification."""
    repo, mgr = repo_for_commits

    test_file = repo / "calculator.py"
    test_file.write_text("def add(a, b): return a + b\n", encoding="utf-8")

    res = mgr.commit_changes(
        files_to_stage=["calculator.py"],
        commit_message="feat(math): add basic addition function",
    )

    assert res.success is True
    assert len(res.commit_hash) == 40
    assert res.branch == "main"
    assert "calculator.py" in res.files_committed
    assert res.message == "feat(math): add basic addition function"

    # Verify working tree is clean
    res_status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=repo, capture_output=True, text=True)
    assert res_status.stdout.strip() == ""


def test_pre_commit_secret_scanning_blocks_commit(repo_for_commits: tuple[Path, CommitManager]) -> None:
    """Verify that staged secrets halt commit execution."""
    repo, mgr = repo_for_commits

    cred_file = repo / "api_client.py"
    cred_file.write_text(
        "API_KEY = 'sk-ant-api03-abcdef123456789012345678'\n"
        "GITHUB_TOKEN = 'ghp_123456789012345678901234567890123456'\n",
        encoding="utf-8",
    )

    with pytest.raises(SecretDetectedInCommitError) as exc_info:
        mgr.commit_changes(
            files_to_stage=["api_client.py"],
            commit_message="feat: add client with hardcoded credentials",
        )

    assert "secrets or credentials" in str(exc_info.value).lower()

    # Verify nothing was committed
    res_head = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True)
    assert "Initial commit" in res_head.stdout


def test_commit_approval_rejection_halts_execution(repo_for_commits: tuple[Path, CommitManager]) -> None:
    """Verify that human rejection prevents commit from executing."""
    repo, _ = repo_for_commits

    unapproved_mgr = CommitManager(
        workspace_root=repo,
        approval_callback=lambda op, details: False,
    )

    new_file = repo / "unapproved.txt"
    new_file.write_text("unapproved work\n", encoding="utf-8")

    with pytest.raises(CommitNotApprovedError):
        unapproved_mgr.commit_changes(
            files_to_stage=["unapproved.txt"],
            commit_message="feat: unapproved commit",
        )

