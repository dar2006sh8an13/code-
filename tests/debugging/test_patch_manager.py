"""Unit tests for PatchManager applying patches atomically, enforcing approval, and rollback."""

from pathlib import Path
import pytest

from codeagent.debugging.fix_generator import FilePatch, ProposedFix
from codeagent.debugging.patch_manager import (
    PatchConflictError,
    PatchManager,
    PatchRejectedError,
)
from codeagent.filesystem.backup import BackupManager


class TestPatchManager:
    """Test suite for PatchManager."""

    def test_apply_patch_approved_creates_backup_and_modifies_file(self, tmp_path: Path) -> None:
        """Apply approved patch atomically and record pre-patch backup."""
        target_file = tmp_path / "math.py"
        target_file.write_text("def div(a, b):\n    return a / b\n", encoding="utf-8")

        backup_mgr = BackupManager(workspace_root=tmp_path)
        mgr = PatchManager(workspace_root=tmp_path, backup_manager=backup_mgr)

        patch = FilePatch(
            file_path="math.py",
            original_content="def div(a, b):\n    return a / b\n",
            modified_content="def div(a, b):\n    return a / b if b != 0 else 0\n",
            diff="--- a/math.py\n+++ b/math.py\n...",
            explanation="Add divisor guard",
        )
        fix = ProposedFix(fix_id="fix1", description="Fix div", patches=[patch])

        records = mgr.apply_fix(fix, approval_callback=lambda p: True)
        assert len(records) == 1
        rec = records[0]
        assert rec.verified is True
        assert rec.target_path == "math.py"

        # Check modified content on disk
        updated_text = target_file.read_text(encoding="utf-8")
        assert "if b != 0 else 0" in updated_text

        # Verify backup was created
        backups = backup_mgr.list_backups()
        assert len(backups) == 1
        assert backups[0].backup_id == rec.backup_id

    def test_approval_rejection_leaves_file_unchanged(self, tmp_path: Path) -> None:
        """Rejecting a patch prevents disk modification and raises PatchRejectedError."""
        target_file = tmp_path / "safe.py"
        original_text = "x = 100\n"
        target_file.write_text(original_text, encoding="utf-8")

        mgr = PatchManager(workspace_root=tmp_path, require_approval=True)
        patch = FilePatch(
            file_path="safe.py",
            original_content=original_text,
            modified_content="x = 200\n",
            diff="...",
            explanation="Change value",
        )
        fix = ProposedFix(fix_id="fix2", description="Change x", patches=[patch])

        with pytest.raises(PatchRejectedError):
            mgr.apply_fix(fix, approval_callback=lambda p: False)

        # File on disk remains strictly untouched
        assert target_file.read_text(encoding="utf-8") == original_text

    def test_patch_conflict_detected_if_file_changed(self, tmp_path: Path) -> None:
        """Raise PatchConflictError if target file content changed since inspection."""
        target_file = tmp_path / "conflict.py"
        target_file.write_text("v1 = 'original'\n", encoding="utf-8")

        mgr = PatchManager(workspace_root=tmp_path)
        # Patch constructed with stale content
        patch = FilePatch(
            file_path="conflict.py",
            original_content="v0 = 'stale'\n",
            modified_content="v2 = 'modified'\n",
            diff="...",
            explanation="Update",
        )
        fix = ProposedFix(fix_id="fix3", description="Update", patches=[patch])

        with pytest.raises(PatchConflictError):
            mgr.apply_fix(fix, bypass_approval=True)

    def test_rollback_restores_original_file(self, tmp_path: Path) -> None:
        """Roll back patch cleanly restores the original file content."""
        target_file = tmp_path / "rollback_test.py"
        original_text = "def greet():\n    return 'Hello'\n"
        target_file.write_text(original_text, encoding="utf-8")

        backup_mgr = BackupManager(workspace_root=tmp_path)
        mgr = PatchManager(workspace_root=tmp_path, backup_manager=backup_mgr)

        patch = FilePatch(
            file_path="rollback_test.py",
            original_content=original_text,
            modified_content="def greet():\n    return 'Bonjour'\n",
            diff="...",
            explanation="Change language",
        )
        fix = ProposedFix(fix_id="fix4", description="Greet", patches=[patch])

        records = mgr.apply_fix(fix, bypass_approval=True)
        assert target_file.read_text(encoding="utf-8") == "def greet():\n    return 'Bonjour'\n"

        # Execute rollback
        success = mgr.rollback_patch(records[0])
        assert success is True
        assert target_file.read_text(encoding="utf-8") == original_text

