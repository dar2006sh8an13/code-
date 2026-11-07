"""Unit tests for scoped memory retrieval and relevance ranking."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.memory.project_memory import ProjectMemoryManager
from codeagent.memory.memory_retriever import MemoryRetriever


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """Fixture providing initialized MemoryStore."""
    store = MemoryStore(db_path=tmp_path / "test_retriever.db")
    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("proj_web", "Web App", "/app", "2026-01-01", "2026-01-01", 1),
    )
    return store


@pytest.fixture
def retriever(memory_store: MemoryStore) -> MemoryRetriever:
    """Fixture providing MemoryRetriever loaded with facts."""
    pm = ProjectMemoryManager(store=memory_store)
    pm.store_fact("proj_web", "architecture", "frontend_framework", "React 19 with Vite and Tailwind", 0.95)
    pm.store_fact("proj_web", "architecture", "backend_framework", "FastAPI with async SQLAlchemy", 0.95)
    pm.store_fact("proj_web", "convention", "docstrings", "Google style docstrings on all functions", 0.8)
    pm.store_fact("proj_web", "dependency", "database", "PostgreSQL 16 with asyncpg driver", 0.9)
    return MemoryRetriever(store=memory_store)


def test_keyword_matching_retrieval(retriever: MemoryRetriever) -> None:
    """Verify retriever surfaces relevant facts based on query keywords."""
    results = retriever.retrieve(project_id="proj_web", query="What database and driver is used?")
    assert len(results) > 0
    top = results[0]
    assert top.key == "database"
    assert "PostgreSQL" in top.value


def test_category_filtered_retrieval(retriever: MemoryRetriever) -> None:
    """Verify category filtering constrains retrieved memory facts."""
    results = retriever.retrieve(project_id="proj_web", query="framework", category="architecture")
    assert len(results) == 2
    for r in results:
        assert r.category == "architecture"


def test_token_budget_limiting(retriever: MemoryRetriever) -> None:
    """Verify retriever respects token limit constraints."""
    results = retriever.retrieve(project_id="proj_web", query="framework", max_tokens=30)
    assert len(results) >= 1

