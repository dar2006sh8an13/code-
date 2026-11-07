"""Centralized single-use, time-bound approval management preventing unauthorized execution and replay attacks."""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import time
from typing import Callable, Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field


class ApprovalDecision(str, Enum):
    """The status of an approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class ApprovalRequest(BaseModel):
    """Formal description of an action presented to a human for authorization."""

    operation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    operation_type: str
    target_repo: Optional[str] = None
    target_paths: List[str] = Field(default_factory=list)
    exact_action: str
    proposed_changes: Optional[str] = None
    potential_risks: str = "Medium risk"
    ttl_seconds: int = 300
    created_at: float = Field(default_factory=time.time)
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        """Check if request exceeded TTL."""
        return (time.time() - self.created_at) > self.ttl_seconds

    def to_display_summary(self) -> str:
        """Format an informative terminal summary for approval confirmation."""
        lines = [
            f"Operation ID:     {self.operation_id}",
            f"Operation Type:   {self.operation_type}",
            f"Action:           {self.exact_action}",
            f"Target Paths:     {', '.join(self.target_paths) if self.target_paths else 'Workspace'}",
            f"Potential Risks:  {self.potential_risks}",
            f"TTL Expiration:   {self.ttl_seconds}s",
        ]
        if self.proposed_changes:
            lines.append(f"Proposed Changes:\n{self.proposed_changes[:500]}")
        return "\n".join(lines)


class ApprovalManager:
    """Coordinates approval lifecycle: request generation, verification, consumption, and expiration."""

    def __init__(
        self,
        default_ttl: int = 300,
        interactive_callback: Optional[Callable[[ApprovalRequest], bool]] = None,
    ) -> None:
        """Initialize ApprovalManager."""
        self.default_ttl = default_ttl
        self.interactive_callback = interactive_callback
        self._requests: Dict[str, ApprovalRequest] = {}

    def create_request(
        self,
        operation_type: str,
        exact_action: str,
        target_paths: Optional[List[str]] = None,
        target_repo: Optional[str] = None,
        proposed_changes: Optional[str] = None,
        potential_risks: str = "Standard mutating operation",
        ttl_seconds: Optional[int] = None,
    ) -> ApprovalRequest:
        """Create a new pending single-use approval request."""
        req = ApprovalRequest(
            operation_type=operation_type,
            exact_action=exact_action,
            target_paths=target_paths or [],
            target_repo=target_repo,
            proposed_changes=proposed_changes,
            potential_risks=potential_risks,
            ttl_seconds=ttl_seconds or self.default_ttl,
        )
        self._requests[req.operation_id] = req
        return req

    def record_decision(
        self,
        operation_id: str,
        approved: bool,
        decided_by: str = "user",
    ) -> ApprovalRequest:
        """Record human approval or rejection."""
        req = self._requests.get(operation_id)
        if not req:
            raise KeyError(f"Approval request '{operation_id}' does not exist.")

        if req.is_expired:
            req.decision = ApprovalDecision.EXPIRED
            raise ValueError(f"Approval request '{operation_id}' has expired.")

        if req.decision != ApprovalDecision.PENDING:
            raise ValueError(f"Approval request '{operation_id}' is already finalized as {req.decision}.")

        req.decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.REJECTED
        req.decided_at = time.time()
        req.decided_by = decided_by
        return req

    def verify_and_consume(self, operation_id: str, expected_type: Optional[str] = None) -> bool:
        """Verify an approval token and mark it CONSUMED to prevent replay attacks.

        Returns True if authorized, False otherwise.
        """
        req = self._requests.get(operation_id)
        if not req:
            return False

        if req.is_expired:
            req.decision = ApprovalDecision.EXPIRED
            return False

        if expected_type and req.operation_type != expected_type:
            return False

        if req.decision == ApprovalDecision.APPROVED:
            # Single-use enforcement: mark CONSUMED
            req.decision = ApprovalDecision.CONSUMED
            return True

        return False

    def request_approval_interactive(
        self,
        operation_type: str,
        exact_action: str,
        target_paths: Optional[List[str]] = None,
        target_repo: Optional[str] = None,
        proposed_changes: Optional[str] = None,
        potential_risks: str = "Mutating operation",
    ) -> bool:
        """Generate request and invoke interactive callback if registered."""
        req = self.create_request(
            operation_type=operation_type,
            exact_action=exact_action,
            target_paths=target_paths,
            target_repo=target_repo,
            proposed_changes=proposed_changes,
            potential_risks=potential_risks,
        )

        if self.interactive_callback:
            decision = self.interactive_callback(req)
            self.record_decision(req.operation_id, approved=decision)
            return self.verify_and_consume(req.operation_id, expected_type=operation_type)

        # In non-interactive mode without callback, default is unapproved
        return False
