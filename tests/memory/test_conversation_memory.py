"""Unit tests for SQLite persistent conversation summaries and memory."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.memory.conversation_memory import ConversationMemoryManager


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """Fixture providing initialized MemoryStore with a project."""
    store = MemoryStore(db_path=tmp_path / "test_conv.db")
    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("test_proj", "Test Project", "/workspace/test", "2026-01-01", "2026-01-01", 1),
    )
    return store


@pytest.fixture
def conv_memory(memory_store: MemoryStore) -> ConversationMemoryManager:
    """Fixture providing ConversationMemoryManager."""
    return ConversationMemoryManager(store=memory_store)


def test_save_and_retrieve_summary(conv_memory: ConversationMemoryManager) -> None:
    """Verify persisting and querying conversation summaries."""
    summary = conv_memory.save_summary(
        project_id="test_proj",
        conversation_id="conv_123",
        summary="User implemented SQLite schema migrations and added unit tests.",
        message_count=12,
    )

    assert bool(summary.id)
    assert summary.project_id == "test_proj"
    assert summary.conversation_id == "conv_123"
    assert "SQLite schema migrations" in summary.summary

    summaries = conv_memory.list_summaries(project_id="test_proj", limit=10)
    assert len(summaries) == 1
    assert summaries[0].summary == summary.summary


def test_multiple_conversations_isolation(conv_memory: ConversationMemoryManager, memory_store: MemoryStore) -> None:
    """Verify summaries are properly scoped to each project without cross-project leakage."""
    memory_store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("other_proj", "Other Project", "/workspace/other", "2026-01-01", "2026-01-01", 0),
    )

    conv_memory.save_summary("test_proj", "conv_a", "Summary for Project A", 4)
    conv_memory.save_summary("other_proj", "conv_b", "Summary for Project B", 6)

    proj_a_summaries = conv_memory.list_summaries("test_proj")
    proj_b_summaries = conv_memory.list_summaries("other_proj")

    assert len(proj_a_summaries) == 1
    assert proj_a_summaries[0].summary == "Summary for Project A"

    assert len(proj_b_summaries) == 1
    assert proj_b_summaries[0].summary == "Summary for Project B"
