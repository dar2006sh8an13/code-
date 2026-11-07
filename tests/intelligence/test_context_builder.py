"""Unit tests for token-budgeted prompt context builder."""

from pathlib import Path
import pytest

from codeagent.memory.memory_store import MemoryStore
from codeagent.memory.memory_manager import MemoryManager
from codeagent.indexing.search_engine import SearchEngine
from codeagent.intelligence.context_builder import ContextBuilder, ProjectContextBundle


@pytest.fixture
def context_env(tmp_path: Path) -> tuple[ContextBuilder, Path]:
    """Fixture providing ContextBuilder with loaded facts and files."""
    proj = tmp_path / "context_proj"
    proj.mkdir()
    (proj / "main.py").write_text("def run(): print('running')\n", encoding="utf-8")

    store = MemoryStore(db_path=tmp_path / "ctx_test.db")
    store.execute_write(
        "INSERT INTO projects (id, name, path, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, ?);",
        ("ctx_p1", "Context Proj", str(proj), "2026-01-01", "2026-01-01", 1),
    )

    mm = MemoryManager(store=store)
    mm.store_fact("ctx_p1", "architecture", "pattern", "MVC Pattern", 0.95)
    mm.store_fact("ctx_p1", "convention", "styling", "PEP8 compliance", 0.8)

    se = SearchEngine(store=store)
    builder = ContextBuilder(memory_manager=mm, search_engine=se)
    return builder, proj


def test_build_context_bundle(context_env: tuple[ContextBuilder, Path]) -> None:
    """Verify context bundle synthesis and markdown prompt formatting."""
    builder, proj = context_env
    bundle = builder.build_context(project_id="ctx_p1", workspace_root=proj, user_query="What architecture?")

    assert bundle.project_name == "Context Proj"
    assert len(bundle.facts) >= 1

    prompt = bundle.to_prompt_context(max_tokens=1000)
    assert "[PROJECT CONTEXT]" in prompt
    assert "Context Proj" in prompt
    assert "MVC Pattern" in prompt

