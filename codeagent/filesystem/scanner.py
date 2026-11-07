"""Directory scanner and tree explorer with depth limits, ceilings, and ignore filters."""

from dataclasses import dataclass, field
import fnmatch
import os
from pathlib import Path
from typing import Optional, Union

from codeagent.filesystem.path_validator import PathValidator


class ScannerError(Exception):
    """Base exception for filesystem scanner operations."""
    pass


DEFAULT_IGNORED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv",
    "venv", "env", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".idea", ".vscode", "dist", "build", ".eggs", ".codeagent",
}

DEFAULT_IGNORED_FILES = {
    ".DS_Store", "Thumbs.db", "*.pyc", "*.pyo", "*.pyd", "*.swp",
}


@dataclass
class DirectoryEntry:
    """Represents a discovered file or directory entry."""

    name: str
    relative_path: str
    is_dir: bool
    size_bytes: int = 0
    extension: str = ""


@dataclass
class ScanResult:
    """Aggregated scan results and metrics for a project directory."""

    root_path: str
    total_files: int
    total_dirs: int
    extension_counts: dict[str, int] = field(default_factory=dict)
    entries: list[DirectoryEntry] = field(default_factory=list)
    tree_view: str = ""
    truncated: bool = False

    def to_summary(self) -> str:
        """Format a summary of directory scan results."""
        ext_summary = ", ".join(f"{ext or '(no ext)'}: {cnt}" for ext, cnt in sorted(self.extension_counts.items(), key=lambda x: x[1], reverse=True)[:8])
        trunc_note = " [Truncated at entry limit]" if self.truncated else ""
        return (
            f"Project Root: {self.root_path}\n"
            f"Directories: {self.total_dirs} | Files: {self.total_files}{trunc_note}\n"
            f"Extensions: {ext_summary or 'None'}"
        )


class DirectoryScanner:
    """Scans and analyzes project directories safely within the workspace boundary."""

    def __init__(
        self,
        validator: Optional[PathValidator] = None,
        max_depth: int = 8,
        max_entries: int = 5000,
        ignored_dirs: Optional[set[str]] = None,
        ignored_files: Optional[set[str]] = None,
    ) -> None:
        """Initialize DirectoryScanner.

        Args:
            validator: PathValidator instance.
            max_depth: Maximum recursion depth for directory traversal.
            max_entries: Total item ceiling to prevent runaway scanning.
            ignored_dirs: Set of directory names to bypass.
            ignored_files: Set of file patterns to bypass.
        """
        self.validator = validator or PathValidator()
        self.max_depth = max_depth
        self.max_entries = max_entries
        self.ignored_dirs = set(ignored_dirs or DEFAULT_IGNORED_DIRS)
        self.ignored_files = set(ignored_files or DEFAULT_IGNORED_FILES)

    def _should_ignore_dir(self, dir_name: str) -> bool:
        """Check if directory name matches ignore rules."""
        if dir_name in self.ignored_dirs:
            return True
        if dir_name.endswith(".egg-info"):
            return True
        return False

    def _should_ignore_file(self, file_name: str) -> bool:
        """Check if filename matches ignore patterns."""
        for pattern in self.ignored_files:
            if fnmatch.fnmatch(file_name, pattern):
                return True
        return False

    def list_directory(
        self,
        target_path: Optional[Union[str, Path]] = None,
        max_depth: int = 1,
    ) -> list[DirectoryEntry]:
        """List files and directories directly inside target_path.

        Args:
            target_path: Directory path within workspace (defaults to workspace root).
            max_depth: Subdirectory recursion depth (default 1 for shallow list).

        Returns:
            list[DirectoryEntry]: Discovered entries sorted alphabetically (directories first).
        """
        path_to_validate = target_path or self.validator.workspace_root
        resolved_path = self.validator.validate_and_resolve(
            path_to_validate,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        if not resolved_path.is_dir():
            raise ScannerError(f"Path '{resolved_path}' is not a directory.")

        entries: list[DirectoryEntry] = []
        try:
            for item in resolved_path.iterdir():
                if item.is_dir():
                    if not self._should_ignore_dir(item.name):
                        rel_p = self.validator.get_relative_display_path(item)
                        entries.append(DirectoryEntry(name=item.name, relative_path=rel_p, is_dir=True))
                else:
                    if not self._should_ignore_file(item.name):
                        rel_p = self.validator.get_relative_display_path(item)
                        size = item.stat().st_size
                        ext = item.suffix.lower()
                        entries.append(
                            DirectoryEntry(
                                name=item.name,
                                relative_path=rel_p,
                                is_dir=False,
                                size_bytes=size,
                                extension=ext,
                            )
                        )
        except PermissionError as exc:
            raise ScannerError(f"Permission denied accessing directory '{resolved_path}': {exc}") from exc

        # Sort: directories first, then alphabetical
        entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        return entries

    def scan_tree(
        self,
        target_path: Optional[Union[str, Path]] = None,
        max_depth: Optional[int] = None,
    ) -> ScanResult:
        """Recursively scan directory tree up to depth and entry ceilings.

        Args:
            target_path: Directory to scan (defaults to workspace root).
            max_depth: Recursion depth limit (defaults to self.max_depth).

        Returns:
            ScanResult: Scan outcome with stats and formatted tree.
        """
        path_to_validate = target_path or self.validator.workspace_root
        resolved_path = self.validator.validate_and_resolve(
            path_to_validate,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        if not resolved_path.is_dir():
            raise ScannerError(f"Target '{resolved_path}' is not a directory.")

        depth_limit = max_depth if max_depth is not None else self.max_depth
        entries: list[DirectoryEntry] = []
        ext_counts: dict[str, int] = {}
        total_files = 0
        total_dirs = 0
        truncated = False

        tree_lines = [f"{resolved_path.name}/"]

        def _traverse(current_dir: Path, current_depth: int, prefix: str = "") -> None:
            nonlocal total_files, total_dirs, truncated

            if current_depth > depth_limit or len(entries) >= self.max_entries:
                if len(entries) >= self.max_entries:
                    truncated = True
                return

            try:
                items = list(current_dir.iterdir())
            except (PermissionError, OSError):
                return

            # Filter ignored items
            valid_dirs = [d for d in items if d.is_dir() and not self._should_ignore_dir(d.name)]
            valid_files = [f for f in items if f.is_file() and not self._should_ignore_file(f.name)]

            valid_dirs.sort(key=lambda d: d.name.lower())
            valid_files.sort(key=lambda f: f.name.lower())

            combined = valid_dirs + valid_files
            count = len(combined)

            for idx, item in enumerate(combined):
                if len(entries) >= self.max_entries:
                    truncated = True
                    return

                is_last = (idx == count - 1)
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "

                rel_p = self.validator.get_relative_display_path(item)

                if item.is_dir():
                    total_dirs += 1
                    entries.append(DirectoryEntry(name=item.name, relative_path=rel_p, is_dir=True))
                    tree_lines.append(f"{prefix}{connector}{item.name}/")
                    _traverse(item, current_depth + 1, prefix + sub_prefix)
                else:
                    total_files += 1
                    ext = item.suffix.lower()
                    size = item.stat().st_size
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                    entries.append(
                        DirectoryEntry(
                            name=item.name,
                            relative_path=rel_p,
                            is_dir=False,
                            size_bytes=size,
                            extension=ext,
                        )
                    )
                    tree_lines.append(f"{prefix}{connector}{item.name}")

        _traverse(resolved_path, 1)

        return ScanResult(
            root_path=self.validator.get_relative_display_path(resolved_path),
            total_files=total_files,
            total_dirs=total_dirs,
            extension_counts=ext_counts,
            entries=entries,
            tree_view="\n".join(tree_lines),
            truncated=truncated,
        )

