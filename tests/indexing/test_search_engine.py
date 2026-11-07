"""Unit tests for multimodal code search engine."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.indexing.search_engine import SearchEngine, SearchResult


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """Fixture with indexed sample records."""
    store = MemoryStore(db_path=tmp_path / "test_search.db")
    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("proj_search", "Search Proj", "/search", "2026-01-01", "2026-01-01", 1),
    )
    # Insert indexed file
    store.execute_write(
        """
        INSERT INTO indexed_files (id, project_id, file_path, file_hash, line_count, file_size_bytes, modified_at, language, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        ("f1", "proj_search", "src/auth/jwt_handler.py", "hash1", 50, 1024, "2026-01-01", "python", "2026-01-01"),
    )
    # Insert symbol
    store.execute_write(
        """
        INSERT INTO code_symbols (project_id, file_id, file_path, name, symbol_type, line_start, line_end, signature, docstring, parent_symbol)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        ("proj_search", "f1", "src/auth/jwt_handler.py", "generate_access_token", "function", 10, 20, "def generate_access_token(user_id: str) -> str", "Generate JWT access token", None),
    )
    # Insert chunk
    store.execute_write(
        """
        INSERT INTO code_chunks (project_id, file_id, file_path, chunk_index, line_start, line_end, content, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        ("proj_search", "f1", "src/auth/jwt_handler.py", 0, 1, 25, "def generate_access_token(user_id: str) -> str:\n    payload = {'sub': user_id}\n    return encode(payload)", "chash1"),
    )
    return store


def test_search_symbol(memory_store: MemoryStore) -> None:
    """Verify searching for functions and classes by symbol name."""
    engine = SearchEngine(store=memory_store)
    results = engine.search_symbol("proj_search", "generate_access_token")

    assert len(results) == 1
    assert results[0].matched_content == "def generate_access_token(user_id: str) -> str"
    assert results[0].line_number == 10


def test_search_filename(memory_store: MemoryStore) -> None:
    """Verify searching for files by path pattern or substring."""
    engine = SearchEngine(store=memory_store)
    results = engine.search_filename("proj_search", "*jwt*")

    assert len(results) == 1
    assert "jwt_handler.py" in results[0].file_path


def test_search_exact_text(memory_store: MemoryStore) -> None:
    """Verify searching exact code content within chunks."""
    engine = SearchEngine(store=memory_store)
    results = engine.search_exact_text("proj_search", "payload = {'sub'")

    assert len(results) == 1
    assert "payload" in results[0].matched_content

