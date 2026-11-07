"""Persistent SQLite and JSONL security audit logger with automated secret redaction."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import List, Optional, Union
import uuid
from pydantic import BaseModel, Field

from codeagent.execution.audit_logger import redact_secrets_text


class SecurityAuditRecord(BaseModel):
    """Immutable audit record of a security-critical operation."""

    id: Optional[int] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    operation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_action: str
    operation_type: str  # "git_commit", "git_branch", "file_edit", "file_delete", "command_exec"
    repo_path: Optional[str] = None
    target_paths: List[str] = Field(default_factory=list)
    permission_decision: str = "ALLOW"  # "ALLOW", "DENY", "REQUIRE_APPROVAL"
    approval_decision: str = "AUTO"     # "APPROVED", "REJECTED", "AUTO", "NONE"
    execution_result: str = "SUCCESS"   # "SUCCESS", "FAILED", "BLOCKED"
    git_commit_hash: Optional[str] = None
    error_message: Optional[str] = None

    def to_sanitized_dict(self) -> dict:
        """Sanitize secrets from record dictionary."""
        d = self.model_dump()
        d["user_action"] = redact_secrets_text(d["user_action"])
        if d.get("error_message"):
            d["error_message"] = redact_secrets_text(d["error_message"])
        return d


class SecurityAuditLogger:
    """Manages append-only security audit events in a dedicated SQLite database and JSONL log."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        audit_storage_path: Union[str, Path] = "data/audit",
        enabled: bool = True,
    ) -> None:
        """Initialize SecurityAuditLogger."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

        a_path = Path(audit_storage_path)
        if a_path.is_absolute():
            self.storage_dir = a_path.resolve()
        else:
            self.storage_dir = (self.workspace_root / a_path).resolve()

        self.enabled = enabled
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "audit.db"
        self.jsonl_path = self.storage_dir / "audit.jsonl"

        self._init_database()

    def _init_database(self) -> None:
        """Initialize SQLite audit schema with WAL mode."""
        if not self.enabled:
            return

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    operation_id TEXT UNIQUE NOT NULL,
                    user_action TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    repo_path TEXT,
                    target_paths TEXT,
                    permission_decision TEXT NOT NULL,
                    approval_decision TEXT NOT NULL,
                    execution_result TEXT NOT NULL,
                    git_commit_hash TEXT,
                    error_message TEXT
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_op_id ON audit_logs(operation_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_op_type ON audit_logs(operation_type);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);")
            conn.commit()

    def log_event(self, record: SecurityAuditRecord) -> SecurityAuditRecord:
        """Record a sanitized security audit event to SQLite and JSONL."""
        if not self.enabled:
            return record

        sanitized = record.to_sanitized_dict()
        paths_json = json.dumps(sanitized["target_paths"])

        # 1. Insert into SQLite
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_logs (
                    timestamp, operation_id, user_action, operation_type, repo_path,
                    target_paths, permission_decision, approval_decision,
                    execution_result, git_commit_hash, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sanitized["timestamp"],
                    sanitized["operation_id"],
                    sanitized["user_action"],
                    sanitized["operation_type"],
                    sanitized["repo_path"],
                    paths_json,
                    sanitized["permission_decision"],
                    sanitized["approval_decision"],
                    sanitized["execution_result"],
                    sanitized["git_commit_hash"],
                    sanitized["error_message"],
                ),
            )
            record.id = cursor.lastrowid
            conn.commit()

        # 2. Append to JSONL for easy line-based streaming and external SIEM ingestion
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sanitized) + "\n")

        return record

    def get_event(self, operation_id: str) -> Optional[SecurityAuditRecord]:
        """Fetch audit event by operation ID."""
        if not self.enabled or not self.db_path.exists():
            return None

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM audit_logs WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if not row:
                return None

            return self._row_to_record(row)

    def list_events(
        self,
        operation_type: Optional[str] = None,
        permission_decision: Optional[str] = None,
        limit: int = 50,
    ) -> List[SecurityAuditRecord]:
        """List and filter audit records descending by timestamp."""
        if not self.enabled or not self.db_path.exists():
            return []

        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []

        if operation_type:
            query += " AND operation_type = ?"
            params.append(operation_type)

        if permission_decision:
            query += " AND permission_decision = ?"
            params.append(permission_decision)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        records: List[SecurityAuditRecord] = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(params)).fetchall()
            for r in rows:
                records.append(self._row_to_record(r))

        return records

    def _row_to_record(self, row: sqlite3.Row) -> SecurityAuditRecord:
        """Convert SQLite row to SecurityAuditRecord."""
        raw_paths = row["target_paths"] or "[]"
        try:
            paths = json.loads(raw_paths)
        except Exception:
            paths = []

        return SecurityAuditRecord(
            id=row["id"],
            timestamp=row["timestamp"],
            operation_id=row["operation_id"],
            user_action=row["user_action"],
            operation_type=row["operation_type"],
            repo_path=row["repo_path"],
            target_paths=paths,
            permission_decision=row["permission_decision"],
            approval_decision=row["approval_decision"],
            execution_result=row["execution_result"],
            git_commit_hash=row["git_commit_hash"],
            error_message=row["error_message"],
        )
