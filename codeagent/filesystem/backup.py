"""Automated atomic backup and restore engine for CodeAgent filesystem modifications."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Optional, Union
import uuid


class BackupError(Exception):
    """Base exception for backup and restore operations."""
    pass


class BackupNotFoundError(BackupError):
    """Raised when a specified backup cannot be located."""
    pass


@dataclass
class BackupMetadata:
    """Metadata describing an automated file backup."""

    backup_id: str
    original_path: str
    backup_file_name: str
    timestamp: str
    sha256: str
    operation: str  # "edit" or "delete"
    size_bytes: int

    def to_dict(self) -> dict:
        """Convert metadata to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BackupMetadata":
        """Instantiate metadata from dictionary."""
        return cls(**data)


class BackupManager:
    """Manages file backups and restoration in a dedicated workspace directory."""

    def __init__(
        self,
        backup_dir: Union[str, Path] = ".codeagent/backups",
        workspace_root: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize BackupManager.

        Args:
            backup_dir: Path to backup storage (relative to workspace or absolute).
            workspace_root: Authoritative workspace root.
        """
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        
        b_path = Path(backup_dir)
        if b_path.is_absolute():
            self.backup_dir = b_path.resolve()
        else:
            self.backup_dir = (self.workspace_root / b_path).resolve()

        self._ensure_backup_dir()

    def _ensure_backup_dir(self) -> None:
        """Create backup directory if it does not already exist."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def create_backup(self, target_path: Path, operation: str = "edit") -> BackupMetadata:
        """Create an atomic backup of target_path before modification or deletion.

        Args:
            target_path: Absolute Path to the existing file.
            operation: Type of operation ("edit" or "delete").

        Returns:
            BackupMetadata: Record of the created backup.

        Raises:
            BackupError: If target file cannot be read or backed up.
        """
        self._ensure_backup_dir()

        if not target_path.exists() or not target_path.is_file():
            raise BackupError(f"Cannot backup non-existent or non-file path: '{target_path}'")

        try:
            timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            unique_token = uuid.uuid4().hex[:8]
            clean_stem = target_path.stem[:30]
            backup_id = f"{timestamp_str}_{clean_stem}_{unique_token}"
            backup_filename = f"{backup_id}{target_path.suffix}"
            backup_dest = self.backup_dir / backup_filename

            # Compute hash and size
            file_hash = self._compute_sha256(target_path)
            file_size = target_path.stat().st_size

            # Atomic copy
            shutil.copy2(target_path, backup_dest)

            # Metadata
            rel_orig = str(target_path.relative_to(self.workspace_root)) if target_path.is_relative_to(self.workspace_root) else str(target_path)
            meta = BackupMetadata(
                backup_id=backup_id,
                original_path=rel_orig,
                backup_file_name=backup_filename,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sha256=file_hash,
                operation=operation,
                size_bytes=file_size,
            )

            # Write metadata manifest file
            meta_path = self.backup_dir / f"{backup_id}.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, indent=2)

            return meta

        except Exception as exc:
            raise BackupError(f"Failed to create backup of '{target_path}': {exc}") from exc

    def list_backups(self) -> list[BackupMetadata]:
        """List all available backups sorted by timestamp descending."""
        if not self.backup_dir.exists():
            return []

        backups: list[BackupMetadata] = []
        for meta_file in self.backup_dir.glob("*.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    backups.append(BackupMetadata.from_dict(data))
            except Exception:
                continue

        backups.sort(key=lambda b: b.timestamp, reverse=True)
        return backups

    def get_backup(self, backup_id: str) -> Optional[BackupMetadata]:
        """Get metadata for a specific backup ID."""
        meta_path = self.backup_dir / f"{backup_id}.json"
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return BackupMetadata.from_dict(data)
        except Exception:
            return None

    def restore_backup(self, backup_id: str, destination_path: Optional[Path] = None) -> Path:
        """Restore a file from a backup ID to its original location or a destination.

        Args:
            backup_id: The ID of the backup to restore.
            destination_path: Optional explicit restore destination.

        Returns:
            Path: The restored file path.

        Raises:
            BackupNotFoundError: If the backup cannot be found.
            BackupError: If restoration fails.
        """
        meta = self.get_backup(backup_id)
        if not meta:
            raise BackupNotFoundError(f"Backup with ID '{backup_id}' not found.")

        backup_file = self.backup_dir / meta.backup_file_name
        if not backup_file.exists():
            raise BackupNotFoundError(f"Backup data file '{meta.backup_file_name}' is missing.")

        target = destination_path or (self.workspace_root / meta.original_path)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, target)
            return target
        except Exception as exc:
            raise BackupError(f"Failed to restore backup '{backup_id}' to '{target}': {exc}") from exc

