"""Unit tests for single-use, time-bound approval management."""

import time
import pytest

from codeagent.safety.approval_manager import (
    ApprovalDecision,
    ApprovalManager,
    ApprovalRequest,
)


def test_approval_request_lifecycle() -> None:
    """Verify standard creation, user approval, and single-use consumption."""
    mgr = ApprovalManager(default_ttl=300)
    req = mgr.create_request(
        operation_type="git_commit",
        exact_action="git commit -m 'feat: test'",
        target_paths=["app.py"],
    )

    assert req.operation_id is not None
    assert req.decision == ApprovalDecision.PENDING

    # Record user approval
    mgr.record_decision(req.operation_id, approved=True)

    # First consumption: authorized
    assert mgr.verify_and_consume(req.operation_id, expected_type="git_commit") is True

    # Replay attempt: rejected because token is now CONSUMED
    assert mgr.verify_and_consume(req.operation_id, expected_type="git_commit") is False


def test_approval_rejection() -> None:
    """Verify that user rejection halts execution."""
    mgr = ApprovalManager()
    req = mgr.create_request(
        operation_type="file_delete",
        exact_action="delete critical.py",
        target_paths=["critical.py"],
    )

    mgr.record_decision(req.operation_id, approved=False)
    assert mgr.verify_and_consume(req.operation_id, expected_type="file_delete") is False


def test_approval_ttl_expiration() -> None:
    """Verify that expired approval tokens are rejected."""
    # Set short TTL
    mgr = ApprovalManager(default_ttl=1)
    req = mgr.create_request(
        operation_type="git_branch",
        exact_action="git branch dev",
        ttl_seconds=1,
    )

    # Fast forward beyond TTL
    req.created_at -= 5
    assert req.is_expired is True

    # Attempting to record or consume should fail
    with pytest.raises(ValueError):
        mgr.record_decision(req.operation_id, approved=True)

    assert mgr.verify_and_consume(req.operation_id) is False


def test_approval_type_mismatch() -> None:
    """Verify that an approval issued for one operation cannot authorize a different operation."""
    mgr = ApprovalManager()
    req = mgr.create_request(
        operation_type="git_branch",
        exact_action="create branch",
    )
    mgr.record_decision(req.operation_id, approved=True)

    # Attempting to consume with expected_type="git_commit" must fail
    assert mgr.verify_and_consume(req.operation_id, expected_type="git_commit") is False

