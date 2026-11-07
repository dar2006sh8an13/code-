"""Lightweight filesystem change watcher tracking created, modified, and deleted project files."""

import hashlib
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from codeagent.filesystem.path_validator import SENSITIVE_FILENAMES


class FileChangeSet(BaseModel):
    """Structured report of detected filesystem modifications."""

    created_files: List[str] = Field(default_factory=list)
    modified_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Return True if any file changes were detected."""
        return bool(self.created_files or self.modified_files or self.deleted_files)

    def to_summary(self) -> str:
        """Format an informative summary of detected changes."""
        return (
            f"Created: {len(self.created_files)}, "
            f"Modified: {len(self.modified_files)}, "
            f"Deleted: {len(self.deleted_files)}"
        )


class FileWatcher:
    """Detects file modifications on demand using modification timestamps and fast hashes."""

    def __init__(
        self,
        workspace_root: Path,
        excluded_dirs: Optional[Set[str]] = None,
        max_file_size_mb: int = 5,
    ) -> None:
        """Initialize FileWatcher.

        Args:
            workspace_root: Directory to monitor.
            excluded_dirs: Directory names to skip (e.g., .git, .venv, node_modules).
            max_file_size_mb: Maximum file size to inspect.
        """
        self.workspace_root = workspace_root.resolve()
        self.excluded_dirs = excluded_dirs or {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            "dist",
            "build",
            ".codeagent",
        }
        self.max_file_bytes = max_file_size_mb * 1024 * 1024
        # State tracking: relative_path -> (mtime, size, quick_hash)
        self._snapshot: Dict[str, Tuple[float, int, str]] = {}

    def _scan_disk(self) -> Dict[str, Tuple[float, int, str]]:
        """Perform a single fast filesystem scan recording timestamps and sizes."""
        new_snapshot: Dict[str, Tuple[float, int, str]] = {}

        if not self.workspace_root.exists() or not self.workspace_root.is_dir():
            return new_snapshot

        for root, dirs, files in os.walk(self.workspace_root):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in self.excluded_dirs and not d.startswith(".")]

            for fname in files:
                # Skip sensitive files and secrets
                if fname in SENSITIVE_FILENAMES or fname.startswith(".env") or fname.endswith((".pyc", ".pyd")):
                    continue

                full_path = Path(root) / fname
                try:
                    stat = full_path.stat()
                    if stat.st_size > self.max_file_bytes:
                        continue

                    rel_path = str(full_path.relative_to(self.workspace_root)).replace("\\", "/")
                    # Compute fast sample hash (first 4KB + size)
                    quick_hash = self._quick_hash(full_path, stat.st_size)
                    new_snapshot[rel_path] = (stat.st_mtime, stat.st_size, quick_hash)
                except (OSError, PermissionError):
                    continue

        return new_snapshot

    def scan_snapshot(self) -> Dict[str, Tuple[float, int, str]]:
        """Scan workspace and update snapshot baseline."""
        self._snapshot = self._scan_disk()
        return self._snapshot

    def detect_changes(self, update_snapshot: bool = True) -> FileChangeSet:
        """Compare current filesystem state with previous snapshot to detect changes."""
        current_state = self._scan_disk()

        created: List[str] = []
        modified: List[str] = []
        deleted: List[str] = []

        # Find created and modified files
        for rel_path, (mtime, size, qhash) in current_state.items():
            if rel_path not in self._snapshot:
                created.append(rel_path)
            else:
                prev_mtime, prev_size, prev_hash = self._snapshot[rel_path]
                if prev_size != size or prev_hash != qhash:
                    modified.append(rel_path)

        # Find deleted files
        for rel_path in self._snapshot:
            if rel_path not in current_state:
                deleted.append(rel_path)

        if update_snapshot:
            self._snapshot = current_state

        return FileChangeSet(
            created_files=sorted(created),
            modified_files=sorted(modified),
            deleted_files=sorted(deleted),
        )

    def reset(self) -> None:
        """Initialize the snapshot to current state without emitting changes."""
        self._snapshot = self.scan_snapshot()

    def _quick_hash(self, path: Path, file_size: int) -> str:
        """Compute quick hash of file header to verify changes without reading entire large files."""
        try:
            with open(path, "rb") as f:
                header = f.read(4096)
                return hashlib.md5(header + str(file_size).encode()).hexdigest()
        except Exception:
            return ""
