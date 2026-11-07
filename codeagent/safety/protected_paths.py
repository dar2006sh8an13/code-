"""Strict protected-path manager preventing traversal, symlink escapes, and unauthorized modifications."""

import fnmatch
import os
from pathlib import Path
from typing import List, Optional, Set, Union
from pydantic import BaseModel, Field

from codeagent.filesystem.path_validator import (
    PathTraversalError,
    PathValidationError,
    RESERVED_DEVICE_NAMES,
    SensitiveFileError,
    WorkspaceSecurityError,
)


class ProtectedPathViolationError(PathValidationError):
    """Raised when an operation targets a protected file or directory."""
    pass


class SymlinkEscapeError(PathValidationError):
    """Raised when a symlink targets a path outside the workspace boundary."""
    pass


class ProtectedPathRule(BaseModel):
    """Description of a protected path pattern or directory."""

    pattern: str
    description: str
    is_custom: bool = False
    is_directory_only: bool = False


class ProtectedPathsManager:
    """Enforces strict path normalization, symlink safety, and protected directory access rules."""

    DEFAULT_PROTECTED_DIRECTORIES = {
        ".git",
        ".env",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".codeagent",
        "data/audit",
        "data/backups",
    }

    DEFAULT_PROTECTED_PATTERNS = {
        "*.pem",
        "*.key",
        "*.pkcs12",
        "*.pfx",
        "*.p12",
        "*.kdbx",
        "id_rsa",
        "id_rsa.pub",
        "id_ed25519",
        "id_ed25519.pub",
        "credentials.json",
        "secrets.json",
        ".netrc",
        ".dockercfg",
    }

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        custom_paths: Optional[List[str]] = None,
    ) -> None:
        """Initialize ProtectedPathsManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.custom_paths: Set[str] = set(custom_paths or [])

    def add_custom_protected_path(self, path_or_pattern: str) -> None:
        """Register a user-defined protected path or glob pattern."""
        clean = path_or_pattern.strip().replace("\\", "/")
        if not clean:
            raise ValueError("Protected path or pattern cannot be empty.")
        self.custom_paths.add(clean)

    def remove_custom_protected_path(self, path_or_pattern: str) -> bool:
        """Remove a user-defined protected path if previously registered."""
        clean = path_or_pattern.strip().replace("\\", "/")
        if clean in self.custom_paths:
            self.custom_paths.remove(clean)
            return True
        return False

    def list_protected_rules(self) -> List[ProtectedPathRule]:
        """List all active default and custom protection rules."""
        rules: List[ProtectedPathRule] = []

        for d in sorted(self.DEFAULT_PROTECTED_DIRECTORIES):
            rules.append(
                ProtectedPathRule(
                    pattern=d,
                    description="Standard system / dependency / internal directory",
                    is_custom=False,
                    is_directory_only=True,
                )
            )

        for p in sorted(self.DEFAULT_PROTECTED_PATTERNS):
            rules.append(
                ProtectedPathRule(
                    pattern=p,
                    description="Sensitive credential or cryptographic key pattern",
                    is_custom=False,
                    is_directory_only=False,
                )
            )

        for c in sorted(self.custom_paths):
            rules.append(
                ProtectedPathRule(
                    pattern=c,
                    description="User-defined custom protected path",
                    is_custom=True,
                    is_directory_only=False,
                )
            )

        return rules

    def validate_path_safety(
        self,
        target_path: Union[str, Path],
        allow_read: bool = False,
    ) -> Path:
        """Normalize path, reject traversal and symlink escapes, and enforce protection rules.

        Args:
            target_path: Relative or absolute path to inspect.
            allow_read: Whether read-only access to certain protected files (e.g. .git config) is allowed.

        Returns:
            Resolved canonical Path.

        Raises:
            PathTraversalError: If traversal sequences are found.
            WorkspaceSecurityError: If resolved path is outside workspace.
            SymlinkEscapeError: If path contains a symlink pointing outside workspace.
            ProtectedPathViolationError: If path matches a protected rule.
        """
        raw_str = str(target_path).strip()
        if not raw_str:
            raise PathValidationError("Path cannot be empty.")

        # Check null byte injection
        if "\0" in raw_str:
            raise PathValidationError("Null byte injection detected in path.")

        # Check Windows reserved device names
        p_obj = Path(raw_str)
        stem = p_obj.stem.upper()
        if stem in RESERVED_DEVICE_NAMES:
            raise PathValidationError(f"Invalid system device name '{stem}' in path.")

        # Resolve path
        if p_obj.is_absolute():
            resolved = p_obj.resolve()
        else:
            resolved = (self.workspace_root / p_obj).resolve()

        # Workspace boundary check
        try:
            rel_path = resolved.relative_to(self.workspace_root)
        except ValueError:
            raise WorkspaceSecurityError(
                f"Path '{resolved}' breaches workspace boundary '{self.workspace_root}'."
            )

        # Check symlink escapes
        curr = resolved
        while curr != self.workspace_root and curr.parent != curr:
            if curr.is_symlink():
                target = curr.resolve()
                try:
                    target.relative_to(self.workspace_root)
                except ValueError:
                    raise SymlinkEscapeError(
                        f"Symlink '{curr}' points outside authorized workspace to '{target}'."
                    )
            curr = curr.parent

        rel_str = str(rel_path).replace("\\", "/")
        name = resolved.name

        # Check default protected directories in path parts
        path_parts = set(rel_path.parts)
        for d in self.DEFAULT_PROTECTED_DIRECTORIES:
            d_parts = set(Path(d).parts)
            if d_parts.issubset(path_parts):
                # When allow_read is True, reading inside .git may be permitted for git query tools
                if allow_read and d == ".git":
                    continue
                raise ProtectedPathViolationError(
                    f"Access to protected directory '{d}' is strictly forbidden by policy (path: '{rel_str}')."
                )

        # Check default sensitive patterns
        for pattern in self.DEFAULT_PROTECTED_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                raise ProtectedPathViolationError(
                    f"Access to sensitive file pattern '{pattern}' is forbidden (file: '{name}')."
                )

        # Check custom paths and patterns
        for c_pat in self.custom_paths:
            if fnmatch.fnmatch(rel_str, c_pat) or fnmatch.fnmatch(name, c_pat):
                raise ProtectedPathViolationError(
                    f"Path '{rel_str}' matches user-defined protected rule '{c_pat}'."
                )

        return resolved

    def is_protected(self, target_path: Union[str, Path], allow_read: bool = False) -> bool:
        """Check whether a target path is protected or forbidden by security policy."""
        try:
            self.validate_path_safety(target_path, allow_read=allow_read)
            return False
        except (PathValidationError, ProtectedPathViolationError, WorkspaceSecurityError, SymlinkEscapeError):
            return True

    def is_path_protected(self, target_path: Union[str, Path], allow_read: bool = False) -> bool:
        """Alias for is_protected."""
        return self.is_protected(target_path, allow_read=allow_read)

