"""Unit tests for full and incremental project indexing."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.indexing.indexer import IndexStatus, ProjectIndexer


@pytest.fixture
def test_project(tmp_path: Path) -> tuple[MemoryStore, Path]:
    """Create a sample project directory with Python source files."""
    proj_dir = tmp_path / "sample_app"
    proj_dir.mkdir()

    (proj_dir / "app.py").write_text(
        "import os\n\ndef main():\n    print('app running')\n",
        encoding="utf-8",
    )
    (proj_dir / "utils.py").write_text(
        "def helper(x: int) -> int:\n    return x * 2\n",
        encoding="utf-8",
    )

    store = MemoryStore(db_path=tmp_path / "test_indexer.db")
    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("proj_idx", "Index Test", str(proj_dir), "2026-01-01", "2026-01-01", 1),
    )
    return store, proj_dir


def test_initial_and_incremental_indexing(test_project: tuple[MemoryStore, Path]) -> None:
    """Verify initial indexing scans files and incremental sync detects modifications."""
    store, proj_dir = test_project
    indexer = ProjectIndexer(store=store, workspace_root=proj_dir)

    # Initial indexing
    status1 = indexer.index_project("proj_idx", rebuild=False)
    assert status1.files_indexed >= 2
    assert status1.total_symbols >= 2
    assert status1.total_chunks >= 2

    # Second run without changes should skip unmodified files
    status2 = indexer.index_project("proj_idx", rebuild=False)
    assert status2.files_indexed == 0

    # Add a new file
    (proj_dir / "extra.py").write_text("def extra_func(): pass\n", encoding="utf-8")
    status3 = indexer.index_project("proj_idx", rebuild=False)
    assert status3.files_indexed == 1


def test_rebuild_indexing(test_project: tuple[MemoryStore, Path]) -> None:
    """Verify rebuild wipes old records and reindexes from scratch."""
    store, proj_dir = test_project
    indexer = ProjectIndexer(store=store, workspace_root=proj_dir)

    indexer.index_project("proj_idx", rebuild=False)
    status_rebuild = indexer.index_project("proj_idx", rebuild=True)
    assert status_rebuild.files_indexed >= 2

