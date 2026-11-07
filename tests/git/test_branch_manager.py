"""Unit tests for Git branch management, ref validation, collision prevention, and dirty-tree guardrails."""

from pathlib import Path
import subprocess
import pytest

from codeagent.git.branch_manager import (
    BranchCollisionError,
    BranchManager,
    BranchNotApprovedError,
    BranchValidationError,
    DirtyWorkingTreeError,
)


@pytest.fixture
def repo_with_branches(tmp_path: Path) -> tuple[Path, BranchManager]:
    """Create a temporary Git repository with an initial commit."""
    repo = tmp_path / "branch_test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    base = repo / "init.txt"
    base.write_text("initial commit\n", encoding="utf-8")
    subprocess.run(["git", "add", "init.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "First commit"], cwd=repo, check=True, capture_output=True)

    mgr = BranchManager(workspace_root=repo)
    return repo, mgr


def test_list_branches(repo_with_branches: tuple[Path, BranchManager]) -> None:
    """Verify listing branches and identifying active branch."""
    repo, mgr = repo_with_branches
    res = mgr.list_branches()

    assert res.current_branch == "main"
    assert len(res.branches) == 1
    assert res.branches[0].name == "main"
    assert res.branches[0].is_current is True


def test_create_branch_success(repo_with_branches: tuple[Path, BranchManager]) -> None:
    """Verify creating a valid branch."""
    repo, mgr = repo_with_branches
    res = mgr.create_branch("feature/test-branch")

    assert res.success is True
    assert res.branch_name == "feature/test-branch"

    b_list = mgr.list_branches()
    names = [b.name for b in b_list.branches]
    assert "feature/test-branch" in names


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "   ",
        "-starts-with-dash",
        "has whitespace",
        "has..double_dot",
        "has~tilde",
        "has^caret",
        "has:colon",
        "has?question",
        "has*star",
        "has[bracket",
        "/leading-slash",
        "trailing-slash/",
        "consecutive//slash",
        "branch.lock",
        "@",
        "HEAD",
    ],
)
def test_branch_name_validation(invalid_name: str) -> None:
    """Verify rejection of invalid ref branch names."""
    with pytest.raises(BranchValidationError):
        BranchManager.validate_branch_name(invalid_name)


def test_branch_collision_prevention(repo_with_branches: tuple[Path, BranchManager]) -> None:
    """Verify collision error when creating an already existing branch."""
    repo, mgr = repo_with_branches
    with pytest.raises(BranchCollisionError):
        mgr.create_branch("main")


def test_dirty_working_tree_prevents_switching(repo_with_branches: tuple[Path, BranchManager]) -> None:
    """Verify switching branches is refused if uncommitted changes would be at risk."""
    repo, mgr = repo_with_branches
    mgr.create_branch("feature/dev")

    # Make working tree dirty
    (repo / "init.txt").write_text("dirty uncommitted change\n", encoding="utf-8")

    with pytest.raises(DirtyWorkingTreeError) as exc_info:
        mgr.switch_branch("feature/dev")

    assert "uncommitted changes" in str(exc_info.value).lower()


def test_switch_branch_success(repo_with_branches: tuple[Path, BranchManager]) -> None:
    """Verify switching to an existing branch on a clean tree."""
    repo, mgr = repo_with_branches
    mgr.create_branch("feature/clean-switch")

    res = mgr.switch_branch("feature/clean-switch")
    assert res.success is True
    assert res.branch_name == "feature/clean-switch"

    b_list = mgr.list_branches()
    assert b_list.current_branch == "feature/clean-switch"


def test_branch_approval_callback_rejection(repo_with_branches: tuple[Path, BranchManager]) -> None:
    """Verify branch creation or switching is halted if approval callback returns False."""
    repo, _ = repo_with_branches
    unapproved_mgr = BranchManager(
        workspace_root=repo,
        approval_callback=lambda op, details: False,
    )

    with pytest.raises(BranchNotApprovedError):
        unapproved_mgr.create_branch("feature/rejected")

