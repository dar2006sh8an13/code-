"""Structured execution audit logger recording operations, approvals, and outcomes."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Optional, Union
import uuid

# Secret patterns to redact from audit logs
SECRET_PATTERNS = [
    (re.compile(r"(password\s*[:=]\s*)([^\s;&]+)", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(secret\s*[:=]\s*)([^\s;&]+)", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(token\s*[:=]\s*)([^\s;&]+)", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(api[_\-\s]?key\s*[:=]\s*)([^\s;&]+)", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)([A-Za-z0-9_\-\.]+)", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(sk-[A-Za-z0-9_\-]{20,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(ghp_[A-Za-z0-9]{36,})"), "[REDACTED_GITHUB_PAT]"),
]


def redact_secrets_text(text: str) -> str:
    """Scrub sensitive credentials, passwords, and tokens from text."""
    scrubbed = text
    for pattern, replacement in SECRET_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


@dataclass
class AuditEntry:
    """Record of a single execution event."""

    execution_id: str
    operation: str
    executable: str
    arguments: list[str]
    working_directory: str
    approval_status: str  # "approved", "rejected", "auto_approved"
    start_time: str
    end_time: str
    exit_code: Optional[int] = None
    timeout: bool = False
    status: str = "success"  # "success", "failed", "timeout", "rejected", "error"
    error_message: Optional[str] = None
    task_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert entry to sanitized dictionary."""
        data = asdict(self)
        # Redact arguments
        data["arguments"] = [redact_secrets_text(arg) for arg in data["arguments"]]
        if data.get("error_message"):
            data["error_message"] = redact_secrets_text(data["error_message"])
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        """Instantiate AuditEntry from dictionary."""
        return cls(**data)


class AuditLogger:
    """Appends structured audit records to a workspace JSONL log file."""

    def __init__(
        self,
        audit_file_path: Union[str, Path] = ".codeagent/audit/execution.jsonl",
        workspace_root: Optional[Union[str, Path]] = None,
        enabled: bool = True,
    ) -> None:
        """Initialize AuditLogger.

        Args:
            audit_file_path: Relative or absolute path to audit log.
            workspace_root: Workspace root for relative resolution.
            enabled: Master switch enabling or disabling file writing.
        """
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        p = Path(audit_file_path)
        if p.is_absolute():
            self.audit_file = p.resolve()
        else:
            self.audit_file = (self.workspace_root / p).resolve()
        self.enabled = enabled

    def _ensure_dir(self) -> None:
        """Create parent directory of audit file if necessary."""
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, entry: AuditEntry) -> None:
        """Append an audit record to the JSONL log file."""
        if not self.enabled:
            return

        try:
            self._ensure_dir()
            with open(self.audit_file, "a", encoding="utf-8") as f:
                json_line = json.dumps(entry.to_dict(), ensure_ascii=False)
                f.write(json_line + "\n")
        except Exception:
            # Audit logging must not crash execution operations
            pass

    def list_entries(self, limit: int = 50) -> list[AuditEntry]:
        """Read recent audit records sorted by start_time descending."""
        if not self.audit_file.exists():
            return []

        entries: list[AuditEntry] = []
        try:
            with open(self.audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        data = json.loads(line_str)
                        entries.append(AuditEntry.from_dict(data))
                    except Exception:
                        continue
        except Exception:
            return []

        entries.sort(key=lambda e: e.start_time, reverse=True)
        return entries[:limit]
