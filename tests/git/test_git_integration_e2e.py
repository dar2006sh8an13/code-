"""End-to-end integration test verifying the complete Phase 8 Git and Safety lifecycle:
1. Initialize isolated repository
2. Modify file and generate verifiable safety backup
3. Inspect Git diff
4. Create branch with approval
5. Stage specific files
6. Attempt commit without approval (fails)
7. Approve and commit (succeeds)
8. Verify resulting commit hash and clean Git status
9. Verify security audit logging
"""

from pathlib import Path
import subprocess
import pytest

from codeagent.config.settings import Settings
from codeagent.git.git_manager import GitManager
from codeagent.git.commit_manager import CommitNotApprovedError
from codeagent.safety.approval_manager import ApprovalManager
from codeagent.safety.backup_manager import SafetyBackupManager
from codeagent.safety.audit_logger import SecurityAuditLogger, SecurityAuditRecord


def test_e2e_git_and_safety_workflow(tmp_path: Path) -> None:
    """Execute complete end-to-end Git and Safety workflow."""
    repo = tmp_path / "e2e_git_repo"
    repo.mkdir()
    backup_dir = tmp_path / "e2e_backups"
    audit_dir = tmp_path / "e2e_audit"

    # 1. Initialize Git repository with initial commit
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "E2EAgent"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@codeagent.local"], cwd=repo, check=True, capture_output=True)

    init_file = repo / "README.md"
    init_file.write_text("# Autonomous Project\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True)

    # Initialize safety components
    settings = Settings(
        git_enabled=True,
        git_require_commit_approval=True,
        backup_storage_path=str(backup_dir),
        audit_storage_path=str(audit_dir),
    )
    backup_mgr = SafetyBackupManager(workspace_root=repo, backup_storage_path=backup_dir)
    audit_logger = SecurityAuditLogger(workspace_root=repo, audit_storage_path=audit_dir)

    # 2. Modify file and create verifiable safety backup
    test_code = repo / "module.py"
    test_code.write_text("def run():\n    return 'v1'\n", encoding="utf-8")
    bak_rec = backup_mgr.create_backup("module.py", operation_id="op_initial_module")
    assert bak_rec is not None
    assert bak_rec.original_rel_path == "module.py"
    assert len(bak_rec.sha256_hash) == 64

    # 3. Create branch with approval
    approval_granted = {"value": True}

    def approval_callback(op: str, details: dict) -> bool:
        return approval_granted["value"]

    git_mgr = GitManager(
        workspace_root=repo,
        settings=settings,
        approval_callback=approval_callback,
    )

    branch_res = git_mgr.create_branch("feature/user-auth", switch=True)
    assert branch_res.success is True
    assert branch_res.branch_name == "feature/user-auth"

    # Verify active branch
    repo_info = git_mgr.get_repository_info()
    assert repo_info.current_branch == "feature/user-auth"

    # 4. Modify file further
    test_code.write_text("def run():\n    return 'v2_authenticated'\n", encoding="utf-8")

    # Verify Git status
    status = git_mgr.get_status()
    assert status.is_clean is False
    assert len(status.untracked_files) == 1

    # 5. Inspect Git diff
    git_mgr.stage_files(["module.py"])
    staged_diff = git_mgr.get_diff(staged=True)
    assert staged_diff.is_staged is True
    assert staged_diff.total_files_changed == 1
    assert "v2_authenticated" in staged_diff.raw_diff

    # 6. Attempt commit without approval -> fails
    approval_granted["value"] = False
    with pytest.raises(CommitNotApprovedError):
        git_mgr.commit_changes(commit_message="feat(auth): add user authentication")

    # 7. Approve and commit -> succeeds
    approval_granted["value"] = True
    commit_res = git_mgr.commit_changes(commit_message="feat(auth): add user authentication")
    assert commit_res.success is True
    assert len(commit_res.commit_hash) == 40
    assert commit_res.branch == "feature/user-auth"
    assert "module.py" in commit_res.files_committed

    # 8. Verify clean working tree after commit
    final_status = git_mgr.get_status()
    assert final_status.is_clean is True

    # 9. Log and verify security audit event
    audit_logger.log_event(
        SecurityAuditRecord(
            user_action="git commit -m 'feat(auth): add user authentication'",
            operation_type="git_commit",
            repo_path=str(repo),
            target_paths=["module.py"],
            permission_decision="REQUIRE_APPROVAL",
            approval_decision="APPROVED",
            execution_result="SUCCESS",
            git_commit_hash=commit_res.commit_hash,
        )
    )

    audit_events = audit_logger.list_events(operation_type="git_commit")
    assert len(audit_events) == 1
    assert audit_events[0].git_commit_hash == commit_res.commit_hash
    assert audit_events[0].approval_decision == "APPROVED"

