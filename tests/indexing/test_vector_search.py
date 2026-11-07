"""Unit tests for local lexical/TF-IDF similarity search."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.indexing.vector_search import VectorSearchEngine


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """Fixture with multiple indexed chunks for similarity ranking."""
    store = MemoryStore(db_path=tmp_path / "test_vec.db")
    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("proj_vec", "Vector Proj", "/vec", "2026-01-01", "2026-01-01", 1),
    )
    # Insert indexed_files records to satisfy foreign keys
    files = [
        ("f1", "proj_vec", "auth.py", "h1", 10, 100, 1.0, "python", "2026-01-01"),
        ("f2", "proj_vec", "database.py", "h2", 10, 100, 1.0, "python", "2026-01-01"),
        ("f3", "proj_vec", "calculator.py", "h3", 10, 100, 1.0, "python", "2026-01-01"),
    ]
    store.execute_many(
        """
        INSERT INTO indexed_files (id, project_id, file_path, file_hash, line_count, file_size_bytes, modified_at, language, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        files,
    )
    chunks = [
        ("f1", "proj_vec", "f1", "auth.py", 0, 1, 10, "def authenticate_user(user, password):\n    check_password_hash(user.hash, password)", "h1"),
        ("f2", "proj_vec", "f2", "database.py", 0, 1, 10, "def connect_postgres_db(dsn):\n    return psycopg2.connect(dsn)", "h2"),
        ("f3", "proj_vec", "f3", "calculator.py", 0, 1, 10, "def add_two_integers(a, b):\n    return a + b", "h3"),
    ]
    store.execute_many(
        """
        INSERT INTO code_chunks (id, project_id, file_id, file_path, chunk_index, line_start, line_end, content, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        chunks,
    )
    return store


def test_lexical_tfidf_similarity_search(memory_store: MemoryStore) -> None:
    """Verify local TF-IDF search returns highest relevance match first."""
    search = VectorSearchEngine(store=memory_store, enabled=False)
    results = search.search_semantic(project_id="proj_vec", query="database postgres connection dsn")

    assert len(results) > 0
    top = results[0]
    assert top.file_path == "database.py"
    assert "connect_postgres_db" in top.matched_content
    assert top.relevance_score > 0.0
