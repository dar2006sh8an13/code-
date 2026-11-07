"""Unit tests for persistent security audit logger, secret redaction, and record retrieval."""

from pathlib import Path
import pytest

from codeagent.safety.audit_logger import SecurityAuditLogger, SecurityAuditRecord


@pytest.fixture
def audit_env(tmp_path: Path) -> tuple[Path, SecurityAuditLogger]:
    """Create a temporary audit directory and SecurityAuditLogger."""
    ws = tmp_path / "audit_workspace"
    ws.mkdir()
    data_dir = tmp_path / "audit_storage"

    logger = SecurityAuditLogger(workspace_root=ws, audit_storage_path=data_dir, enabled=True)
    return ws, logger


def test_audit_log_and_query_events(audit_env: tuple[Path, SecurityAuditLogger]) -> None:
    """Verify logging events and querying them from SQLite."""
    ws, logger = audit_env

    rec1 = SecurityAuditRecord(
        user_action="git commit -m 'feat: initial'",
        operation_type="git_commit",
        permission_decision="REQUIRE_APPROVAL",
        approval_decision="APPROVED",
        execution_result="SUCCESS",
        git_commit_hash="abc1234567890abcdef1234567890abcdef12",
    )
    logger.log_event(rec1)

    rec2 = SecurityAuditRecord(
        user_action="git branch dev",
        operation_type="git_branch",
        permission_decision="REQUIRE_APPROVAL",
        approval_decision="APPROVED",
        execution_result="SUCCESS",
    )
    logger.log_event(rec2)

    # Query events
    events = logger.list_events()
    assert len(events) == 2
    assert events[0].operation_type == "git_branch"
    assert events[1].operation_type == "git_commit"

    # Query by operation ID
    found = logger.get_event(rec1.operation_id)
    assert found is not None
    assert found.git_commit_hash == "abc1234567890abcdef1234567890abcdef12"


def test_audit_secret_redaction(audit_env: tuple[Path, SecurityAuditLogger]) -> None:
    """Verify passwords, keys, and tokens are scrubbed from stored records."""
    ws, logger = audit_env

    rec = SecurityAuditRecord(
        user_action="connect API api-key=sk-ant-12345678901234567890 password=supersecret",
        operation_type="config",
        permission_decision="ALLOW",
        approval_decision="AUTO",
        execution_result="SUCCESS",
        error_message="failed with token=ghp_123456789012345678901234567890123456",
    )
    logger.log_event(rec)

    queried = logger.get_event(rec.operation_id)
    assert queried is not None
    assert "supersecret" not in queried.user_action
    assert "[REDACTED]" in queried.user_action
    assert "ghp_" not in queried.error_message

