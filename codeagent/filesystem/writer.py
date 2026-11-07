"""Safe file writer with overwrite protection, atomic writes, and parent directory guards."""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Optional, Union

from codeagent.filesystem.backup import BackupManager
from codeagent.filesystem.path_validator import PathValidator


class FileWriterError(Exception):
    """Base exception for file writing operations."""
    pass


class FileAlreadyExistsError(FileWriterError):
    """Raised when writing to an existing file without explicit overwrite approval."""
    pass


@dataclass
class WriteResult:
    """Structured result returned by FileWriter."""

    path: str
    bytes_written: int
    created_new: bool
    overwritten: bool
    backup_id: Optional[str] = None

    def to_summary(self) -> str:
        """Format a concise summary of the write operation."""
        action = "Created" if self.created_new else "Overwritten"
        backup_str = f" (backup: {self.backup_id})" if self.backup_id else ""
        return f"{action} file '{self.path}' ({self.bytes_written} bytes written){backup_str}"


class FileWriter:
    """Safely creates and writes files within the workspace boundary."""

    def __init__(
        self,
        validator: Optional[PathValidator] = None,
        backup_manager: Optional[BackupManager] = None,
    ) -> None:
        """Initialize FileWriter.

        Args:
            validator: PathValidator instance.
            backup_manager: Optional BackupManager instance for automated backups before overwrite.
        """
        self.validator = validator or PathValidator()
        self.backup_manager = backup_manager

    def write(
        self,
        target_path: Union[str, Path],
        content: str,
        overwrite: bool = False,
        create_parents: bool = True,
    ) -> WriteResult:
        """Create or overwrite a file safely with atomic writes.

        Args:
            target_path: Target file path within workspace.
            content: Text content to write in UTF-8.
            overwrite: If False, raises error if file already exists.
            create_parents: If True, creates missing parent directories.

        Returns:
            WriteResult: Structured outcome of the write operation.

        Raises:
            FileAlreadyExistsError: If file exists and overwrite is False.
            FileWriterError: If parent dir cannot be created or on write failure.
        """
        resolved_path = self.validator.validate_and_resolve(
            target_path,
            allow_nonexistent=True,
            check_sensitive=True,
        )

        exists = resolved_path.exists()
        backup_id: Optional[str] = None

        if exists:
            if not resolved_path.is_file():
                raise FileWriterError(f"Target path '{resolved_path}' exists and is a directory.")
            if not overwrite:
                raise FileAlreadyExistsError(
                    f"File '{self.validator.get_relative_display_path(resolved_path)}' already exists. "
                    "Set overwrite=True or confirm replacement to overwrite."
                )
            # Create backup if manager is available
            if self.backup_manager:
                meta = self.backup_manager.create_backup(resolved_path, operation="edit")
                backup_id = meta.backup_id

        parent_dir = resolved_path.parent
        if not parent_dir.exists():
            if not create_parents:
                raise FileWriterError(f"Parent directory '{parent_dir}' does not exist.")
            parent_dir.mkdir(parents=True, exist_ok=True)

        # Atomic write via temporary file in the same directory
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=parent_dir,
                delete=False,
            ) as tf:
                tf.write(content)
                temp_file = Path(tf.name)

            # Atomic rename / replace
            os.replace(temp_file, resolved_path)
            temp_file = None  # Replaced successfully

            bytes_written = len(content.encode("utf-8"))
            rel_display = self.validator.get_relative_display_path(resolved_path)

            return WriteResult(
                path=rel_display,
                bytes_written=bytes_written,
                created_new=not exists,
                overwritten=exists,
                backup_id=backup_id,
            )

        except Exception as exc:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise FileWriterError(f"Failed to write file '{resolved_path}': {exc}") from exc

