"""Unit tests for safety file backup snapshots, SHA-256 integrity checks, and restoration conflict detection."""

from pathlib import Path
import time
import pytest

from codeagent.safety.backup_manager import (
    BackupConflictError,
    BackupError,
    BackupIntegrityError,
    SafetyBackupManager,
)


@pytest.fixture
def backup_env(tmp_path: Path) -> tuple[Path, SafetyBackupManager]:
    """Create a temporary workspace and SafetyBackupManager."""
    ws = tmp_path / "backup_workspace"
    ws.mkdir()
    data_dir = tmp_path / "backups_storage"

    mgr = SafetyBackupManager(workspace_root=ws, backup_storage_path=data_dir)
    return ws, mgr


def test_create_and_restore_backup(backup_env: tuple[Path, SafetyBackupManager]) -> None:
    """Verify standard file backup creation and integrity restoration."""
    ws, mgr = backup_env

    target = ws / "important.py"
    target.write_text("print('original content')\n", encoding="utf-8")

    rec = mgr.create_backup("important.py")
    assert rec is not None
    assert rec.original_rel_path == "important.py"
    assert rec.size_bytes > 0
    assert len(rec.sha256_hash) == 64

    # Now modify original
    target.write_text("print('corrupted or modified content')\n", encoding="utf-8")

    # Restore from backup
    res = mgr.restore_backup(rec.backup_id, force=True)
    assert res.success is True
    assert target.read_text(encoding="utf-8") == "print('original content')\n"


def test_backup_integrity_validation(backup_env: tuple[Path, SafetyBackupManager]) -> None:
    """Verify that tampered backup archives fail SHA-256 integrity validation."""
    ws, mgr = backup_env

    target = ws / "secure.txt"
    target.write_text("secret hash check\n", encoding="utf-8")

    rec = mgr.create_backup("secure.txt")
    assert rec is not None

    # Tamper with the archived backup file directly
    archive_file = mgr.storage_dir / rec.backup_file_rel_path
    archive_file.write_text("tampered malicious bytes\n", encoding="utf-8")

    with pytest.raises(BackupIntegrityError) as exc:
        mgr.restore_backup(rec.backup_id, force=True)

    assert "corrupted" in str(exc.value).lower()


def test_restore_conflict_detection(backup_env: tuple[Path, SafetyBackupManager]) -> None:
    """Verify that restoring warns if the target file has newer modifications."""
    ws, mgr = backup_env

    target = ws / "code.py"
    target.write_text("version 1\n", encoding="utf-8")

    rec = mgr.create_backup("code.py")
    assert rec is not None

    # Wait briefly and update file
    time.sleep(0.05)
    target.write_text("version 2 modified\n", encoding="utf-8")

    # Attempt restore without force -> should raise BackupConflictError
    with pytest.raises(BackupConflictError):
        mgr.restore_backup(rec.backup_id, force=False)

    # Force restore succeeds
    res = mgr.restore_backup(rec.backup_id, force=True)
    assert res.success is True
    assert target.read_text(encoding="utf-8") == "version 1\n"


def test_missing_backup_raises_error(backup_env: tuple[Path, SafetyBackupManager]) -> None:
    """Verify querying or restoring nonexistent backup ID raises BackupError."""
    _, mgr = backup_env
    with pytest.raises(BackupError):
        mgr.restore_backup("bak_nonexistent_id")

