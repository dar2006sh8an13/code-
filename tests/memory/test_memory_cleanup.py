"""Unit tests for memory cleanup, deduplication, and secret scrubbing."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.memory.memory_cleanup import MemoryCleanupManager


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """Fixture providing initialized MemoryStore."""
    store = MemoryStore(db_path=tmp_path / "test_cleanup.db")
    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("proj_clean", "Clean Project", "/clean", "2026-01-01", "2026-01-01", 1),
    )
    return store


@pytest.fixture
def cleanup_mgr(memory_store: MemoryStore) -> MemoryCleanupManager:
    """Fixture providing MemoryCleanupManager."""
    return MemoryCleanupManager(store=memory_store)


def test_purge_secrets_from_existing_memories(cleanup_mgr: MemoryCleanupManager, memory_store: MemoryStore) -> None:
    """Verify purge_secrets scrubs existing secrets from the database."""
    # Insert an unscrubbed memory directly
    memory_store.execute_write(
        """
        INSERT INTO project_memories (id, project_id, category, key, value, source, confidence, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        ("m1", "proj_clean", "general", "leaked_secret", "API key: sk-ant-api03-abcdef1234567890abcdef1234567890abcdef", "test", 1.0, "2026-01-01", "2026-01-01"),
    )

    scrubbed_count = cleanup_mgr.purge_secrets()
    assert scrubbed_count == 1

    row = memory_store.execute_query_one("SELECT value FROM project_memories WHERE key = 'leaked_secret';")
    assert "sk-ant-api03" not in row["value"]
    assert "[REDACTED" in row["value"]


def test_vacuum_and_cleanup(cleanup_mgr: MemoryCleanupManager) -> None:
    """Verify vacuum execution runs without errors."""
    cleanup_mgr.vacuum_database()
