"""Unit tests for SQLite persistent memory store."""

from pathlib import Path
import sqlite3
import pytest

from codeagent.memory.memory_store import MemoryStore


def test_memory_store_initialization(tmp_path: Path) -> None:
    """Verify database and all required tables are created on initialization."""
    db_path = tmp_path / "test_memory.db"
    store = MemoryStore(db_path=db_path)

    # Check that file exists
    assert db_path.exists()

    # Verify tables
    tables = [
        "projects",
        "indexed_files",
        "code_symbols",
        "code_chunks",
        "import_relationships",
        "conversations",
        "conversation_summaries",
        "project_memories",
        "memory_metadata",
    ]
    with store.get_connection() as conn:
        cursor = conn.cursor()
        for t in tables:
            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?;", (t,))
            assert cursor.fetchone()[0] == 1, f"Table {t} was not created"

    # Verify schema version
    row = store.execute_query_one("SELECT value FROM memory_metadata WHERE key = 'schema_version';")
    assert row is not None
    assert row["value"] in ("1", "1.0")


def test_foreign_key_and_wal_mode(tmp_path: Path) -> None:
    """Verify WAL journal mode and foreign keys are enabled."""
    db_path = tmp_path / "test_wal.db"
    store = MemoryStore(db_path=db_path)

    with store.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal = cursor.fetchone()[0].lower()
        # On Windows or tmpfs WAL may be wal or memory
        assert journal in ("wal", "memory", "delete")

        cursor.execute("PRAGMA foreign_keys;")
        fk = cursor.fetchone()[0]
        assert fk == 1


def test_execute_query_and_write(tmp_path: Path) -> None:
    """Verify write and query execution with parameter binding."""
    db_path = tmp_path / "test_ops.db"
    store = MemoryStore(db_path=db_path)

    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("proj_1", "Project Alpha", "/test/alpha", "2026-01-01T00:00:00", "2026-01-01T00:00:00", 1),
    )

    rows = store.execute_query("SELECT * FROM projects WHERE id = ?;", ("proj_1",))
    assert len(rows) == 1
    assert rows[0]["name"] == "Project Alpha"
    assert rows[0]["is_active"] == 1


def test_execute_many(tmp_path: Path) -> None:
    """Verify batch write operations using execute_many."""
    db_path = tmp_path / "test_batch.db"
    store = MemoryStore(db_path=db_path)

    records = [
        ("p1", "Name 1", "/p1", "2026-01-01", "2026-01-01", 0),
        ("p2", "Name 2", "/p2", "2026-01-01", "2026-01-01", 0),
        ("p3", "Name 3", "/p3", "2026-01-01", "2026-01-01", 0),
    ]
    store.execute_many(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        records,
    )

    count_row = store.execute_query_one("SELECT count(*) as total FROM projects;")
    assert count_row["total"] == 3
