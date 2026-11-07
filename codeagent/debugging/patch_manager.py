"""Patch manager applying approved code repairs atomically with backups and rollback."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Callable, List, Optional, Union
import uuid

from codeagent.debugging.fix_generator import FilePatch, ProposedFix
from codeagent.filesystem.backup import BackupManager
from codeagent.filesystem.path_validator import PathValidator, WorkspaceSecurityError
from codeagent.filesystem.reader import FileReader


class PatchError(Exception):
    """Base exception for patch operations."""
    pass


class PatchRejectedError(PatchError):
    """Raised when user rejects proposed patch."""
    pass


class PatchConflictError(PatchError):
    """Raised when file on disk has changed since proposal inspection."""
    pass


class PatchVerificationError(PatchError):
    """Raised when file content verification fails post-patch."""
    pass


@dataclass
class PatchRecord:
    """Audit record of an applied patch."""

    patch_id: str
    target_path: str
    backup_id: str
    applied_at: str
    diff: str
    verified: bool
    rolled_back: bool = False

    def to_dict(self) -> dict:
        """Convert record to dictionary."""
        return asdict(self)


class PatchManager:
    """Manages patch validation, user approval gates, atomic writes, backups, and rollback."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        backup_manager: Optional[BackupManager] = None,
        path_validator: Optional[PathValidator] = None,
        reader: Optional[FileReader] = None,
        require_approval: bool = True,
    ) -> None:
        """Initialize PatchManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.validator = path_validator or PathValidator(workspace_root=self.workspace_root)
        self.reader = reader or FileReader(validator=self.validator)
        self.backup_manager = backup_manager or BackupManager(workspace_root=self.workspace_root)
        self.require_approval = require_approval
        self._history: List[PatchRecord] = []

    def apply_fix(
        self,
        proposed_fix: ProposedFix,
        approval_callback: Optional[Callable[[FilePatch], bool]] = None,
        bypass_approval: bool = False,
    ) -> List[PatchRecord]:
        """Apply all patches in a ProposedFix after validation and approval."""
        if not proposed_fix.is_valid:
            raise PatchError(f"Cannot apply invalid fix: {proposed_fix.validation_error}")

        if not proposed_fix.patches:
            raise PatchError("Proposed fix contains no file patches.")

        applied_records: List[PatchRecord] = []

        for patch in proposed_fix.patches:
            record = self.apply_single_patch(
                patch=patch,
                approval_callback=approval_callback,
                bypass_approval=bypass_approval,
            )
            applied_records.append(record)

        return applied_records

    def apply_single_patch(
        self,
        patch: FilePatch,
        approval_callback: Optional[Callable[[FilePatch], bool]] = None,
        bypass_approval: bool = False,
    ) -> PatchRecord:
        """Apply a single FilePatch atomically with pre-patch backup."""
        resolved = self.validator.validate_and_resolve(patch.file_path, allow_nonexistent=False)

        # 1. Verify file content on disk has not diverged from patch's original_content
        current_content = self.reader.read(resolved).content
        if current_content != patch.original_content:
            raise PatchConflictError(
                f"File '{patch.file_path}' has changed on disk since diagnostic inspection. "
                "Patch application aborted to prevent clobbering concurrent changes."
            )

        # 2. Enforce human user approval
        if self.require_approval and not bypass_approval:
            if not approval_callback:
                raise PatchRejectedError(
                    f"Approval required for patch on '{patch.file_path}', but no approval callback was provided."
                )
            user_decision = approval_callback(patch)
            if not user_decision:
                raise PatchRejectedError(f"User rejected patch for '{patch.file_path}'.")

        # 3. Create pre-patch atomic backup
        backup_meta = self.backup_manager.create_backup(resolved, operation="patch")

        # 4. Atomic write via temporary file
        temp_dir = resolved.parent
        fd, temp_file_path = tempfile.mkstemp(dir=str(temp_dir), prefix=".patch_tmp_")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(patch.modified_content)
            # Atomic rename / replace
            os.replace(temp_file_path, str(resolved))
        except Exception as exc:
            if os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass
            raise PatchError(f"Atomic file write failed for '{patch.file_path}': {exc}") from exc

        # 5. Verify file on disk post-write
        verified_content = self.reader.read(resolved).content
        if verified_content != patch.modified_content:
            # Automatic emergency rollback
            self.backup_manager.restore_backup(backup_meta.backup_id)
            raise PatchVerificationError(
                f"Verification failed after patching '{patch.file_path}'. Automatically restored backup."
            )

        record = PatchRecord(
            patch_id=uuid.uuid4().hex[:8],
            target_path=str(resolved.relative_to(self.workspace_root)),
            backup_id=backup_meta.backup_id,
            applied_at=datetime.now(timezone.utc).isoformat(),
            diff=patch.diff,
            verified=True,
            rolled_back=False,
        )
        self._history.append(record)
        return record

    def rollback_patch(self, patch_record: PatchRecord) -> bool:
        """Roll back an applied patch using its recorded backup ID."""
        if patch_record.rolled_back:
            return True

        self.backup_manager.restore_backup(patch_record.backup_id)
        patch_record.rolled_back = True
        return True

    def rollback_all(self, records: List[PatchRecord]) -> int:
        """Roll back a series of patches in reverse order."""
        count = 0
        for rec in reversed(records):
            if self.rollback_patch(rec):
                count += 1
        return count

    def list_applied_patches(self) -> List[PatchRecord]:
        """Return list of all patches applied in active session."""
        return list(self._history)
