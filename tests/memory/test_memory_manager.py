"""Unit tests for central MemoryManager coordinator."""

from pathlib import Path
import pytest

from codeagent.config.settings import Settings
from codeagent.memory.memory_manager import MemoryManager


@pytest.fixture
def memory_manager(tmp_path: Path) -> MemoryManager:
    """Fixture providing MemoryManager with tmp_path storage."""
    cfg = Settings(project_data_path=str(tmp_path))
    mm = MemoryManager(settings=cfg)
    mm.store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("proj_1", "Project 1", "/p1", "2026-01-01", "2026-01-01", 1),
    )
    return mm


def test_memory_manager_facade(memory_manager: MemoryManager) -> None:
    """Verify facade functions for fact storing, listing, retrieving, and conversation summaries."""
    # Store fact
    fact = memory_manager.store_fact(
        project_id="proj_1",
        category="convention",
        key="naming",
        value="snake_case for functions and variables",
    )
    assert bool(fact.id)

    # List facts
    facts = memory_manager.list_facts(project_id="proj_1")
    assert len(facts) == 1
    assert facts[0].key == "naming"

    # Retrieve memories
    results = memory_manager.retrieve_memories(project_id="proj_1", query="function naming rules")
    assert len(results) == 1
    assert results[0].key == "naming"

    # Save and list conversation summary
    summary = memory_manager.save_conversation_summary(
        project_id="proj_1",
        conversation_id="conv_a",
        summary="Refactored database queries for efficiency",
        message_count=8,
    )
    assert bool(summary.id)

    summaries = memory_manager.list_conversation_summaries(project_id="proj_1")
    assert len(summaries) == 1
