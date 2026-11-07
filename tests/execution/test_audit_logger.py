"""Unit tests for AuditLogger and secret redaction."""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from codeagent.execution.audit_logger import AuditEntry, AuditLogger, redact_secrets_text


class TestAuditLogger:
    """Test suite for AuditLogger serialization, redaction, and persistence."""

    def test_secret_redaction_text(self) -> None:
        sample = "Connecting with password=super_secret_123 and token=abc123xyz"
        redacted = redact_secrets_text(sample)
        assert "super_secret_123" not in redacted
        assert "abc123xyz" not in redacted
        assert "[REDACTED]" in redacted

    def test_audit_log_writing_and_reading(self, tmp_path: Path) -> None:
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(audit_file_path=log_file, workspace_root=tmp_path)

        entry = AuditEntry(
            execution_id="exec_001",
            operation="python",
            executable="python",
            arguments=["app.py", "password=secret99"],
            working_directory=str(tmp_path),
            approval_status="approved",
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=datetime.now(timezone.utc).isoformat(),
            exit_code=0,
            timeout=False,
            status="success",
        )

        logger.log(entry)
        assert log_file.exists()

        entries = logger.list_entries()
        assert len(entries) == 1
        assert entries[0].execution_id == "exec_001"
        assert "secret99" not in str(entries[0].arguments)
        assert "[REDACTED]" in str(entries[0].arguments)

