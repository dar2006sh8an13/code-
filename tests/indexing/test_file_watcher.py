"""Unit tests for file change detector."""

from pathlib import Path
import time
import pytest

from codeagent.indexing.file_watcher import FileChangeSet, FileWatcher


def test_file_watcher_detects_created_and_modified(tmp_path: Path) -> None:
    """Verify watcher detects created, modified, and deleted files across snapshots."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    f1 = workspace / "file1.py"
    f1.write_text("print('hello')", encoding="utf-8")

    watcher = FileWatcher(workspace_root=workspace)
    # First snapshot records initial state
    watcher.scan_snapshot()

    # Create new file
    f2 = workspace / "file2.py"
    f2.write_text("print('world')", encoding="utf-8")

    # Modify file1
    time.sleep(0.05)
    f1.write_text("print('hello modified')", encoding="utf-8")

    changes = watcher.detect_changes()
    assert "file2.py" in changes.created_files
    assert "file1.py" in changes.modified_files
    assert len(changes.deleted_files) == 0


def test_file_watcher_detects_deleted(tmp_path: Path) -> None:
    """Verify watcher detects deleted files."""
    workspace = tmp_path / "workspace_del"
    workspace.mkdir()

    f1 = workspace / "temp.py"
    f1.write_text("temp content", encoding="utf-8")

    watcher = FileWatcher(workspace_root=workspace)
    watcher.scan_snapshot()

    f1.unlink()

    changes = watcher.detect_changes()
    assert "temp.py" in changes.deleted_files

