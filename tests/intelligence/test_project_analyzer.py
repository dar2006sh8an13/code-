"""Unit tests for comprehensive project analyzer."""

from pathlib import Path
import pytest

from codeagent.intelligence.project_analyzer import ComprehensiveProjectAnalysis, ProjectAnalyzer


def test_analyze_fastapi_project(tmp_path: Path) -> None:
    """Verify detection of FastAPI project with Docker and pytest."""
    proj = tmp_path / "fastapi_app"
    proj.mkdir()

    (proj / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (proj / "requirements.txt").write_text("fastapi>=0.100.0\nuvicorn>=0.20.0\n", encoding="utf-8")
    (proj / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "test_main.py").write_text("def test_read_main(): pass\n", encoding="utf-8")

    analyzer = ProjectAnalyzer()
    analysis = analyzer.analyze(proj)

    assert analysis.project_type == "FastAPI Web Application"
    assert "FastAPI" in analysis.frameworks
    assert "main.py" in analysis.entry_points
    assert "Docker" in analysis.deployment_configs
    assert analysis.primary_language == "Python"


def test_analyze_react_node_project(tmp_path: Path) -> None:
    """Verify detection of React / Vite frontend project."""
    proj = tmp_path / "react_app"
    proj.mkdir()

    (proj / "package.json").write_text(
        """{
  "name": "react-frontend",
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "vite": "^5.0.0"
  }
}""",
        encoding="utf-8",
    )
    (proj / "src").mkdir()
    (proj / "src" / "App.tsx").write_text("export const App = () => <div>Hello</div>;\n", encoding="utf-8")
    (proj / "vite.config.ts").write_text("import { defineConfig } from 'vite';\n", encoding="utf-8")

    analyzer = ProjectAnalyzer()
    analysis = analyzer.analyze(proj)

    assert "React" in analysis.frameworks
    assert "Vite" in analysis.build_systems
    assert analysis.primary_language in ("TypeScript", "JavaScript")

