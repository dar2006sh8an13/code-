"""CodeAgent Safety & Protection subsystem enforcing permissions, path boundaries, approvals, and audits."""

from codeagent.safety.approval_manager import (
    ApprovalDecision,
    ApprovalManager,
    ApprovalRequest,
)
from codeagent.safety.audit_logger import (
    SecurityAuditLogger,
    SecurityAuditRecord,
)
from codeagent.safety.backup_manager import (
    BackupConflictError,
    BackupError,
    BackupIntegrityError,
    BackupRecord,
    RestoreResult,
    SafetyBackupManager,
)
from codeagent.safety.permission_manager import (
    PermissionEvaluationResult,
    PolicyVerdict,
    SafetyPermissionManager,
)
from codeagent.safety.protected_paths import (
    ProtectedPathRule,
    ProtectedPathsManager,
    ProtectedPathViolationError,
    SymlinkEscapeError,
)

__all__ = [
    "ApprovalDecision",
    "ApprovalManager",
    "ApprovalRequest",
    "BackupConflictError",
    "BackupError",
    "BackupIntegrityError",
    "BackupRecord",
    "PermissionEvaluationResult",
    "PolicyVerdict",
    "ProtectedPathRule",
    "ProtectedPathsManager",
    "ProtectedPathViolationError",
    "RestoreResult",
    "SafetyBackupManager",
    "SafetyPermissionManager",
    "SecurityAuditLogger",
    "SecurityAuditRecord",
    "SymlinkEscapeError",
]
