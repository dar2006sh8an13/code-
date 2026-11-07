"""Strict workspace path security and traversal validation for CodeAgent."""

import os
from pathlib import Path
from typing import Optional, Union


class PathValidationError(Exception):
    """Base exception for filesystem path validation errors."""
    pass


class PathTraversalError(PathValidationError):
    """Raised when directory traversal is detected."""
    pass


class WorkspaceSecurityError(PathValidationError):
    """Raised when access outside the configured workspace boundary is attempted."""
    pass


class SensitiveFileError(PathValidationError):
    """Raised when access to a protected sensitive file is attempted."""
    pass


class InvalidPathError(PathValidationError):
    """Raised when an invalid, illegal, or reserved system path is provided."""
    pass


# Windows reserved device names
RESERVED_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

# Sensitive file and directory patterns
SENSITIVE_NAMES = {
    ".env", ".git", ".ssh", ".gnupg", ".netrc", ".dockercfg",
}
SENSITIVE_FILENAMES = SENSITIVE_NAMES

SENSITIVE_EXTENSIONS = {
    ".pem", ".key", ".pkcs12", ".pfx", ".p12", ".kdbx",
}


class PathValidator:
    """Validates paths against workspace boundaries and sensitive file rules."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        allow_sensitive_reads: bool = False,
    ) -> None:
        """Initialize PathValidator with an authoritative workspace root."""
        if workspace_root:
            self.workspace_root = Path(workspace_root).resolve()
        else:
            self.workspace_root = Path.cwd().resolve()
        self.allow_sensitive_reads = allow_sensitive_reads

    def validate_and_resolve(
        self,
        target_path: Union[str, Path],
        allow_nonexistent: bool = True,
        check_sensitive: bool = True,
    ) -> Path:
        """Resolve a target path safely within the workspace boundary.

        Args:
            target_path: Relative or absolute path to validate.
            allow_nonexistent: If True, target need not exist on disk yet (e.g. for creating new files).
            check_sensitive: If True, block access to sensitive and secret files.

        Returns:
            Path: Canonical absolute Path guaranteed inside workspace.

        Raises:
            InvalidPathError: For null bytes or Windows reserved names.
            WorkspaceSecurityError: If target path escapes workspace boundary.
            PathTraversalError: If traversal escapes workspace.
            SensitiveFileError: If accessing protected sensitive files.
            FileNotFoundError: If allow_nonexistent is False and file does not exist.
        """
        raw_str = str(target_path).strip()
        if not raw_str:
            raise InvalidPathError("Path cannot be empty.")

        # Check for null bytes
        if "\0" in raw_str:
            raise InvalidPathError("Illegal null byte in path.")

        path_obj = Path(raw_str)

        # Check Windows reserved device names in components
        for part in path_obj.parts:
            stem = part.split(".")[0].upper()
            if stem in RESERVED_DEVICE_NAMES:
                raise InvalidPathError(f"Reserved device name '{stem}' cannot be used in filesystem paths.")

        # Resolve path
        if path_obj.is_absolute():
            resolved = path_obj.resolve()
        else:
            resolved = (self.workspace_root / path_obj).resolve()

        # Check containment within workspace_root
        # Handle Windows case-insensitive comparisons cleanly
        ws_str = os.path.normcase(str(self.workspace_root))
        res_str = os.path.normcase(str(resolved))

        # Check if resolved path is the workspace root or inside it
        try:
            common = os.path.commonpath([ws_str, res_str])
            if common != ws_str:
                raise WorkspaceSecurityError(
                    f"Access denied: Target path '{resolved}' escapes workspace root '{self.workspace_root}'."
                )
        except ValueError:
            # e.g., Different Windows drive letters (C: vs D:)
            raise WorkspaceSecurityError(
                f"Access denied: Target path '{resolved}' is on a different drive than workspace root '{self.workspace_root}'."
            )

        # Check existence if required
        if not allow_nonexistent and not resolved.exists():
            raise FileNotFoundError(f"File or directory not found: '{resolved}'")

        # Check sensitive file protection
        if check_sensitive and self.is_sensitive(resolved):
            raise SensitiveFileError(
                f"Protected sensitive file: Access to '{resolved.name}' is strictly forbidden."
            )

        return resolved

    def is_sensitive(self, target_path: Union[str, Path]) -> bool:
        """Check if a path matches sensitive files or credentials."""
        path_obj = Path(target_path)
        name_lower = path_obj.name.lower()

        # Check exact sensitive names
        if name_lower in SENSITIVE_NAMES:
            return True

        # Check .env variants (.env.local, .env.production, etc.)
        if name_lower.startswith(".env"):
            return True

        # Check parts for sensitive directories (.git, .ssh, etc.)
        for part in path_obj.parts:
            part_lower = part.lower()
            if part_lower in SENSITIVE_NAMES:
                return True

        # Check sensitive extensions
        suffix_lower = path_obj.suffix.lower()
        if suffix_lower in SENSITIVE_EXTENSIONS:
            return True

        # Check private key identifiers
        if any(token in name_lower for token in ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"]):
            return True

        # Check secret keyword in filename
        if any(secret_word in name_lower for secret_word in ["credential", "secret_key", "private_key"]):
            return True

        return False

    def is_inside_workspace(self, target_path: Union[str, Path]) -> bool:
        """Return True if the target path is inside workspace, False otherwise."""
        try:
            self.validate_and_resolve(target_path, allow_nonexistent=True, check_sensitive=False)
            return True
        except (PathValidationError, ValueError):
            return False

    def get_relative_display_path(self, target_path: Path) -> str:
        """Return a clean relative path string for display or logging."""
        try:
            return str(target_path.relative_to(self.workspace_root))
        except ValueError:
            return str(target_path)

