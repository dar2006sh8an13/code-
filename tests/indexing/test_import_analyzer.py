"""Unit tests for AST import analysis and circular dependency detection."""

from pathlib import Path
import pytest

from codeagent.indexing.import_analyzer import ImportAnalyzer, ImportRelation, ModuleDependencyGraph


def test_python_import_extraction() -> None:
    """Verify extracting import and from-import statements with line numbers."""
    code = """import os
import sys as system
from pathlib import Path, PurePath
from codeagent.config.settings import Settings
"""
    analyzer = ImportAnalyzer()
    relations = analyzer.extract_imports(code=code, file_path="main.py", language="python")

    modules = {r.imported_module: r for r in relations}
    assert "os" in modules
    assert "sys" in modules
    assert "pathlib" in modules
    assert "Path" in modules["pathlib"].imported_symbols
    assert "codeagent.config.settings" in modules


def test_circular_dependency_detection() -> None:
    """Verify cycle detection in module dependency graph."""
    graph = ModuleDependencyGraph()
    # Cycle: a -> b -> c -> a
    graph.add_dependency("module_a", "module_b")
    graph.add_dependency("module_b", "module_c")
    graph.add_dependency("module_c", "module_a")
    graph.add_dependency("module_d", "module_a")

    cycles = graph.find_circular_dependencies()
    assert len(cycles) > 0
    # The cycle contains module_a, module_b, module_c
    found_cycle = any("module_a" in c and "module_b" in c and "module_c" in c for c in cycles)
    assert found_cycle


def test_acyclic_graph_reports_no_cycles() -> None:
    """Verify DAG has no circular dependencies."""
    graph = ModuleDependencyGraph()
    graph.add_dependency("main", "service")
    graph.add_dependency("service", "repo")
    graph.add_dependency("repo", "db")

    cycles = graph.find_circular_dependencies()
    assert len(cycles) == 0

