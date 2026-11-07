"""Safe individual file deleter with mandatory confirmation and automatic pre-delete backups."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from codeagent.filesystem.backup import BackupManager
from codeagent.filesystem.path_validator import PathValidator


class DeleterError(Exception):
    """Base exception for file deletion operations."""
    pass


class DeletionNotConfirmedError(DeleterError):
    """Raised when file deletion is not explicitly confirmed by the user."""
    pass


class DirectoryDeletionBlockedError(DeleterError):
    """Raised when an attempt is made to delete a directory."""
    pass


@dataclass
class DeleteResult:
    """Structured outcome of a file deletion operation."""

    path: str
    backup_id: str
    deleted: bool

    def to_summary(self) -> str:
        """Format a summary of the deletion result."""
        return f"Deleted file '{self.path}' (backup preserved: {self.backup_id})"


class FileDeleter:
    """Safely deletes individual files within workspace with mandatory user confirmation."""

    def __init__(
        self,
        validator: Optional[PathValidator] = None,
        backup_manager: Optional[BackupManager] = None,
    ) -> None:
        """Initialize FileDeleter.

        Args:
            validator: PathValidator instance.
            backup_manager: BackupManager instance for pre-delete backup.
        """
        self.validator = validator or PathValidator()
        self.backup_manager = backup_manager or BackupManager(workspace_root=self.validator.workspace_root)

    def delete(
        self,
        target_path: Union[str, Path],
        confirmed: bool = False,
        confirmation_callback: Optional[Callable[[Path], bool]] = None,
    ) -> DeleteResult:
        """Delete an individual file safely.

        Args:
            target_path: File path within workspace.
            confirmed: Explicit confirmation flag.
            confirmation_callback: Optional user confirmation callback.

        Returns:
            DeleteResult: Result with backup ID.

        Raises:
            FileNotFoundError: If target file does not exist.
            DirectoryDeletionBlockedError: If target is a directory.
            DeletionNotConfirmedError: If deletion is not confirmed.
            DeleterError: On deletion failure.
        """
        resolved_path = self.validator.validate_and_resolve(
            target_path,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        # Strictly disallow deleting directories
        if resolved_path.is_dir():
            raise DirectoryDeletionBlockedError(
                f"Cannot delete directory '{resolved_path.name}'. FileDeleter operates strictly on individual files."
            )

        if not resolved_path.is_file():
            raise DeleterError(f"Target '{resolved_path}' is not a regular file.")

        display_name = self.validator.get_relative_display_path(resolved_path)

        # Check confirmation
        is_confirmed = confirmed
        if not is_confirmed and confirmation_callback:
            is_confirmed = confirmation_callback(resolved_path)

        if not is_confirmed:
            raise DeletionNotConfirmedError(
                f"Deletion of '{display_name}' was not confirmed. File was NOT deleted."
            )

        # Create automatic backup before deletion
        backup_meta = self.backup_manager.create_backup(resolved_path, operation="delete")

        try:
            resolved_path.unlink()
            return DeleteResult(
                path=display_name,
                backup_id=backup_meta.backup_id,
                deleted=True,
            )
        except Exception as exc:
            raise DeleterError(f"Failed to delete file '{display_name}': {exc}") from exc

