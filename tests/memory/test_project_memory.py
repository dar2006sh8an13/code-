"""Unit tests for project knowledge and persistent facts management."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.memory.project_memory import ProjectFact, ProjectMemoryManager


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """Fixture providing initialized MemoryStore."""
    return MemoryStore(db_path=tmp_path / "test_facts.db")


@pytest.fixture
def project_memory(memory_store: MemoryStore) -> ProjectMemoryManager:
    """Fixture providing ProjectMemoryManager instance."""
    memory_store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("test_proj", "Test Project", "/workspace/test", "2026-01-01", "2026-01-01", 1),
    )
    return ProjectMemoryManager(store=memory_store)


def test_store_and_retrieve_fact(project_memory: ProjectMemoryManager) -> None:
    """Verify storing and retrieving project knowledge facts."""
    fact = project_memory.store_fact(
        project_id="test_proj",
        category="architecture",
        key="pattern",
        value="Clean Architecture with repository pattern",
        confidence=0.95,
        source="analysis",
    )

    assert bool(fact.id)
    assert fact.project_id == "test_proj"
    assert fact.category == "architecture"
    assert fact.key == "pattern"

    retrieved = project_memory.get_fact(project_id="test_proj", category="architecture", key="pattern")
    assert retrieved is not None
    assert retrieved.value == "Clean Architecture with repository pattern"
    assert retrieved.confidence == 0.95


def test_update_existing_fact_confidence(project_memory: ProjectMemoryManager) -> None:
    """Verify that updating an existing fact updates value and confidence."""
    f1 = project_memory.store_fact(
        project_id="test_proj",
        category="dependency",
        key="orm",
        value="SQLAlchemy 2.0",
        confidence=0.7,
    )

    f2 = project_memory.store_fact(
        project_id="test_proj",
        category="dependency",
        key="orm",
        value="SQLAlchemy 2.0.30 Async Engine",
        confidence=0.98,
    )

    facts = project_memory.list_facts(project_id="test_proj", category="dependency")
    assert len(facts) == 1
    assert facts[0].value == "SQLAlchemy 2.0.30 Async Engine"
    assert facts[0].confidence == 0.98


def test_secret_scrubbing_in_facts(project_memory: ProjectMemoryManager) -> None:
    """Verify secrets (API keys, passwords) are scrubbed before storage."""
    fact = project_memory.store_fact(
        project_id="test_proj",
        category="general",
        key="api_config",
        value="Authorization header: Bearer sk-ant-api03-1234567890abcdef1234567890abcdef",
    )

    retrieved = project_memory.get_fact(project_id="test_proj", category="general", key="api_config")
    assert retrieved is not None
    assert "sk-ant-api03" not in retrieved.value
    assert "[REDACTED" in retrieved.value


def test_delete_fact(project_memory: ProjectMemoryManager) -> None:
    """Verify deleting a fact by ID or key."""
    fact = project_memory.store_fact(
        project_id="test_proj",
        category="limitation",
        key="concurrency",
        value="Single-threaded execution only",
    )

    success = project_memory.delete_fact(fact_id=fact.id)
    assert success is True

    retrieved = project_memory.get_fact(project_id="test_proj", category="limitation", key="concurrency")
    assert retrieved is None
