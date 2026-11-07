"""Unit tests for project architecture mapper."""

from pathlib import Path
import pytest

from codeagent.intelligence.architecture_mapper import ArchitectureMap, ArchitectureMapper, ProjectLayer


def test_layer_mapping_and_report(tmp_path: Path) -> None:
    """Verify source files are classified into architectural layers."""
    proj = tmp_path / "layered_app"
    (proj / "cli").mkdir(parents=True)
    (proj / "api").mkdir(parents=True)
    (proj / "models").mkdir(parents=True)
    (proj / "tests").mkdir(parents=True)

    (proj / "cli" / "main.py").write_text("import typer\n", encoding="utf-8")
    (proj / "api" / "routes.py").write_text("from fastapi import APIRouter\n", encoding="utf-8")
    (proj / "models" / "user.py").write_text("class User: pass\n", encoding="utf-8")
    (proj / "tests" / "test_api.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    mapper = ArchitectureMapper()
    arch_map = mapper.map_project(proj)

    assert len(arch_map.layers) >= 3
    layer_types = {layer.layer_type for layer in arch_map.layers}
    assert "CLI" in layer_types or "Presentation" in layer_types
    assert "Tests" in layer_types or "Testing" in layer_types

