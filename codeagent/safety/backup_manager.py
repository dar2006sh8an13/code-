"""Safety backup manager creating pre-modification file snapshots with SHA-256 integrity validation and conflict protection."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from typing import List, Optional, Union
import uuid
from pydantic import BaseModel, Field

from codeagent.filesystem.path_validator import WorkspaceSecurityError
from codeagent.safety.protected_paths import ProtectedPathsManager


class BackupError(Exception):
    """Base exception for safety backup operations."""
    pass


class BackupIntegrityError(BackupError):
    """Raised when a backup archive fails SHA-256 integrity verification."""
    pass


class BackupConflictError(BackupError):
    """Raised when restoring would overwrite a file modified since backup without confirmation."""
    pass


class BackupRecord(BaseModel):
    """Complete metadata describing a secured file backup."""

    backup_id: str
    original_rel_path: str
    backup_file_rel_path: str
    created_at: str
    sha256_hash: str
    operation_id: Optional[str] = None
    size_bytes: int = 0
    file_mtime: float = 0.0

    def to_summary(self) -> str:
        """Formatted summary of the backup record."""
        return (
            f"Backup ID: {self.backup_id} | File: {self.original_rel_path}\n"
            f"Timestamp: {self.created_at} | Size: {self.size_bytes}B | SHA256: {self.sha256_hash[:12]}..."
        )


class RestoreResult(BaseModel):
    """Result of restoring a file from safety backup."""

    success: bool
    backup_id: str
    target_path: str
    restored_bytes: int
    message: str = ""


class SafetyBackupManager:
    """Creates verifiable file backups before mutating operations and manages integrity-checked restoration."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        backup_storage_path: Union[str, Path] = "data/backups",
        protected_paths_mgr: Optional[ProtectedPathsManager] = None,
    ) -> None:
        """Initialize SafetyBackupManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

        b_path = Path(backup_storage_path)
        if b_path.is_absolute():
            self.storage_dir = b_path.resolve()
        else:
            self.storage_dir = (self.workspace_root / b_path).resolve()

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir = self.storage_dir / "meta"
        self.files_dir = self.storage_dir / "files"
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

        self.protected_mgr = protected_paths_mgr or ProtectedPathsManager(self.workspace_root)

    def _compute_sha256(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file contents."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def create_backup(
        self,
        target_path: Union[str, Path],
        operation_id: Optional[str] = None,
    ) -> Optional[BackupRecord]:
        """Create a verifiable safety backup of an existing workspace file.

        Args:
            target_path: File to back up.
            operation_id: Optional tracking identifier for the mutating operation.

        Returns:
            BackupRecord if file exists and was backed up, None if file does not exist yet.
        """
        # Validate path safety
        resolved = self.protected_mgr.validate_path_safety(target_path, allow_read=True)
        if not resolved.exists() or not resolved.is_file():
            # If target does not exist yet (e.g. creating new file), no backup needed
            return None

        rel_path = str(resolved.relative_to(self.workspace_root)).replace("\\", "/")
        backup_id = f"bak_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc).isoformat()

        sha256 = self._compute_sha256(resolved)
        size_bytes = resolved.stat().st_size
        mtime = resolved.stat().st_mtime

        # Store backup file with backup_id prefix
        archive_name = f"{backup_id}_{resolved.name}"
        archive_path = self.files_dir / archive_name
        shutil.copy2(resolved, archive_path)

        rec = BackupRecord(
            backup_id=backup_id,
            original_rel_path=rel_path,
            backup_file_rel_path=str(archive_path.relative_to(self.storage_dir)).replace("\\", "/"),
            created_at=created_at,
            sha256_hash=sha256,
            operation_id=operation_id,
            size_bytes=size_bytes,
            file_mtime=mtime,
        )

        # Write metadata JSON
        meta_file = self.meta_dir / f"{backup_id}.json"
        meta_file.write_text(rec.model_dump_json(indent=2), encoding="utf-8")

        return rec

    def list_backups(self, file_path_filter: Optional[str] = None) -> List[BackupRecord]:
        """List all available backup records sorted by timestamp descending."""
        records: List[BackupRecord] = []
        for meta_p in self.meta_dir.glob("*.json"):
            try:
                data = json.loads(meta_p.read_text(encoding="utf-8"))
                rec = BackupRecord.model_validate(data)
                if file_path_filter:
                    filter_clean = file_path_filter.strip().replace("\\", "/")
                    if filter_clean not in rec.original_rel_path:
                        continue
                records.append(rec)
            except Exception:
                continue

        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def get_backup(self, backup_id: str) -> Optional[BackupRecord]:
        """Retrieve a specific backup record by ID."""
        meta_file = self.meta_dir / f"{backup_id}.json"
        if not meta_file.exists():
            return None
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            return BackupRecord.model_validate(data)
        except Exception:
            return None

    def restore_backup(
        self,
        backup_id: str,
        force: bool = False,
    ) -> RestoreResult:
        """Restore a file from safety backup verifying SHA-256 integrity and mtime conflict checks.

        Args:
            backup_id: Unique identifier of backup.
            force: If True, override modification conflict warnings.
        """
        rec = self.get_backup(backup_id)
        if not rec:
            raise BackupError(f"Backup with ID '{backup_id}' not found.")

        archive_file = self.storage_dir / rec.backup_file_rel_path
        if not archive_file.exists():
            raise BackupError(f"Archived backup content file '{archive_file}' is missing.")

        # 1. Verify SHA-256 integrity of archived copy
        actual_sha = self._compute_sha256(archive_file)
        if actual_sha != rec.sha256_hash:
            raise BackupIntegrityError(
                f"Backup '{backup_id}' corrupted! Stored SHA256 {rec.sha256_hash} != computed {actual_sha}."
            )

        target_file = (self.workspace_root / rec.original_rel_path).resolve()
        # Verify target is still safe
        self.protected_mgr.validate_path_safety(target_file, allow_read=False)

        # 2. Check conflict: has target file been modified since backup was created?
        if target_file.exists() and not force:
            curr_sha = self._compute_sha256(target_file)
            if curr_sha != rec.sha256_hash:
                curr_mtime = target_file.stat().st_mtime
                if curr_mtime > rec.file_mtime:
                    raise BackupConflictError(
                        f"Conflict detected for '{rec.original_rel_path}': File was modified after backup was created. "
                        "Restoring will overwrite newer modifications. Pass force=True or confirm in CLI to proceed."
                    )

        # 3. Restore atomically
        target_file.parent.mkdir(parents=True, exist_ok=True)
        temp_dest = target_file.with_name(f"{target_file.name}.restoring_{uuid.uuid4().hex[:6]}")
        shutil.copy2(archive_file, temp_dest)
        temp_dest.replace(target_file)

        return RestoreResult(
            success=True,
            backup_id=backup_id,
            target_path=rec.original_rel_path,
            restored_bytes=rec.size_bytes,
            message=f"Restored '{rec.original_rel_path}' successfully from backup '{backup_id}'.",
        )
