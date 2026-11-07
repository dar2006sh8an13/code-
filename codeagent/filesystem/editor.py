"""File editor with unified diff generation, interactive user approvals, and atomic updates."""

from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import tempfile
from typing import Callable, Optional, Union

from codeagent.filesystem.backup import BackupManager
from codeagent.filesystem.path_validator import PathValidator
from codeagent.filesystem.reader import FileReader


class FileEditorError(Exception):
    """Base exception for file editing operations."""
    pass


class EditNotApprovedError(FileEditorError):
    """Raised when an edit proposal is rejected or not approved."""
    pass


class TargetNotFoundError(FileEditorError):
    """Raised when search target cannot be located in the source file."""
    pass


class VerificationError(FileEditorError):
    """Raised when the updated file fails verification after write."""
    pass


@dataclass
class EditProposal:
    """A proposed edit including original content, modified content, and unified diff."""

    target_path: Path
    display_path: str
    original_content: str
    modified_content: str
    diff: str
    has_changes: bool


@dataclass
class EditResult:
    """Outcome of an approved and applied file edit."""

    path: str
    diff: str
    backup_id: str
    bytes_modified: int
    verified: bool

    def to_summary(self) -> str:
        """Format a summary of the applied edit."""
        return (
            f"Successfully edited '{self.path}' "
            f"({self.bytes_modified} bytes, backup ID: {self.backup_id}, verified: {self.verified})"
        )


class FileEditor:
    """Manages diff generation, user approvals, backups, and atomic file editing."""

    def __init__(
        self,
        validator: Optional[PathValidator] = None,
        backup_manager: Optional[BackupManager] = None,
        reader: Optional[FileReader] = None,
    ) -> None:
        """Initialize FileEditor.

        Args:
            validator: PathValidator instance.
            backup_manager: BackupManager instance.
            reader: FileReader instance.
        """
        self.validator = validator or PathValidator()
        self.backup_manager = backup_manager or BackupManager(workspace_root=self.validator.workspace_root)
        self.reader = reader or FileReader(validator=self.validator)

    @staticmethod
    def generate_unified_diff(original: str, modified: str, file_label: str = "file") -> str:
        """Generate a standard unified diff string between original and modified text."""
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                mod_lines,
                fromfile=f"a/{file_label}",
                tofile=f"b/{file_label}",
                lineterm="",
            )
        )
        return "\n".join(diff_lines)

    def propose_edit(
        self,
        target_path: Union[str, Path],
        new_content: Optional[str] = None,
        search_target: Optional[str] = None,
        replacement: Optional[str] = None,
    ) -> EditProposal:
        """Prepare an edit proposal and generate a unified diff without applying changes to disk.

        Args:
            target_path: Path to the file to edit.
            new_content: Complete replacement content, OR
            search_target: Substring to locate, combined with:
            replacement: Replacement substring.

        Returns:
            EditProposal: Proposal containing unified diff and modified content.

        Raises:
            FileNotFoundError: If target file does not exist.
            TargetNotFoundError: If search_target is not in original file.
            FileEditorError: If parameters are invalid.
        """
        resolved_path = self.validator.validate_and_resolve(
            target_path,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        read_res = self.reader.read(resolved_path)
        original_content = read_res.content

        if new_content is not None:
            modified_content = new_content
        elif search_target is not None and replacement is not None:
            if search_target not in original_content:
                raise TargetNotFoundError(
                    f"Search target string not found in '{read_res.path}'."
                )
            modified_content = original_content.replace(search_target, replacement)
        else:
            raise FileEditorError("Must provide either 'new_content' or both 'search_target' and 'replacement'.")

        display_name = read_res.path
        diff = self.generate_unified_diff(original_content, modified_content, display_name)
        has_changes = original_content != modified_content

        return EditProposal(
            target_path=resolved_path,
            display_path=display_name,
            original_content=original_content,
            modified_content=modified_content,
            diff=diff,
            has_changes=has_changes,
        )

    def apply_proposal(
        self,
        proposal: EditProposal,
        approved: bool = False,
        approval_callback: Optional[Callable[[EditProposal], bool]] = None,
    ) -> EditResult:
        """Apply an edit proposal atomically after verifying approval.

        Args:
            proposal: The generated EditProposal.
            approved: If True, bypasses approval callback.
            approval_callback: Optional callback receiving proposal and returning bool.

        Returns:
            EditResult: Result with backup ID and verification status.

        Raises:
            EditNotApprovedError: If approval is rejected.
            VerificationError: If modified file fails post-write verification.
            FileEditorError: On write failure.
        """
        if not proposal.has_changes:
            return EditResult(
                path=proposal.display_path,
                diff="",
                backup_id="",
                bytes_modified=0,
                verified=True,
            )

        # Check approval
        is_approved = approved
        if not is_approved and approval_callback:
            is_approved = approval_callback(proposal)

        if not is_approved:
            raise EditNotApprovedError(
                f"Edit to '{proposal.display_path}' was not approved by user."
            )

        # 1. Create automatic backup before edit
        backup_meta = self.backup_manager.create_backup(proposal.target_path, operation="edit")

        # 2. Atomic write
        parent_dir = proposal.target_path.parent
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=parent_dir,
                delete=False,
            ) as tf:
                tf.write(proposal.modified_content)
                temp_file = Path(tf.name)

            os.replace(temp_file, proposal.target_path)
            temp_file = None

        except Exception as exc:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise FileEditorError(f"Failed to apply edit to '{proposal.target_path}': {exc}") from exc

        # 3. Post-write verification
        try:
            with open(proposal.target_path, "r", encoding="utf-8") as f:
                saved_content = f.read()

            if saved_content != proposal.modified_content:
                raise VerificationError(
                    f"Post-write verification failed for '{proposal.display_path}': content on disk does not match."
                )
        except Exception as exc:
            raise VerificationError(f"Verification check failed: {exc}") from exc

        bytes_modified = len(proposal.modified_content.encode("utf-8"))
        return EditResult(
            path=proposal.display_path,
            diff=proposal.diff,
            backup_id=backup_meta.backup_id,
            bytes_modified=bytes_modified,
            verified=True,
        )

