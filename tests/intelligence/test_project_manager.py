"""Unit tests for ProjectManager multi-project coordinator and context isolation."""

from pathlib import Path
import pytest

from codeagent.config.settings import Settings
from codeagent.memory.memory_manager import MemoryManager
from codeagent.intelligence.project_manager import ProjectManager, ProjectRecord


@pytest.fixture
def project_manager(tmp_path: Path) -> tuple[ProjectManager, Path, Path]:
    """Fixture providing ProjectManager with two initialized project directories."""
    proj1 = tmp_path / "project_alpha"
    proj1.mkdir()
    (proj1 / "alpha.py").write_text("def alpha(): return 'alpha'\n", encoding="utf-8")

    proj2 = tmp_path / "project_beta"
    proj2.mkdir()
    (proj2 / "beta.py").write_text("def beta(): return 'beta'\n", encoding="utf-8")

    cfg = Settings(project_data_path=str(tmp_path / "data"))
    mm = MemoryManager(settings=cfg)
    pm = ProjectManager(memory_manager=mm, settings=cfg)

    pm.register_project(path=proj1, name="Alpha", set_active=True)
    pm.register_project(path=proj2, name="Beta", set_active=False)

    return pm, proj1, proj2


def test_project_registration_and_listing(project_manager: tuple[ProjectManager, Path, Path]) -> None:
    """Verify projects are recorded in SQLite and listed."""
    pm, p1, p2 = project_manager
    projects = pm.list_projects()

    assert len(projects) == 2
    names = {p.name for p in projects}
    assert "Alpha" in names
    assert "Beta" in names


def test_project_switching_and_context_isolation(project_manager: tuple[ProjectManager, Path, Path]) -> None:
    """Verify switching active project isolates facts and indexes without cross-project leakage."""
    pm, p1, p2 = project_manager

    # Currently Alpha is active
    pm.switch_project("Alpha")
    alpha_id = pm.active_project_id
    pm.memory_manager.store_fact(alpha_id, "decision", "auth", "OAuth2 with JWT")

    # Switch to Beta
    pm.switch_project("Beta")
    beta_id = pm.active_project_id
    pm.memory_manager.store_fact(beta_id, "decision", "auth", "Session Cookies with Redis")

    # Verify facts are isolated
    alpha_facts = pm.memory_manager.list_facts(alpha_id)
    beta_facts = pm.memory_manager.list_facts(beta_id)

    assert len(alpha_facts) == 1
    assert "OAuth2" in alpha_facts[0].value
    assert "Session Cookies" not in alpha_facts[0].value

    assert len(beta_facts) == 1
    assert "Session Cookies" in beta_facts[0].value
    assert "OAuth2" not in beta_facts[0].value

