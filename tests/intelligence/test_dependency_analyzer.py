"""Unit tests for non-executing dependency manifest analyzer."""

from pathlib import Path
import pytest

from codeagent.intelligence.dependency_analyzer import DependencyAnalyzer, DependencyReport


def test_parse_requirements_txt(tmp_path: Path) -> None:
    """Verify parsing pip requirements.txt file."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(
        """# Requirements
fastapi>=0.110.0
uvicorn[standard]==0.29.0
pydantic>=2.5.0
# Commented package
# requests==2.31.0
pytest
""",
        encoding="utf-8",
    )

    analyzer = DependencyAnalyzer()
    deps = analyzer.parse_requirements_file(req_file)

    dep_map = {d.name: d for d in deps}
    assert "fastapi" in dep_map
    assert dep_map["fastapi"].version_spec == ">=0.110.0"
    assert "uvicorn" in dep_map
    assert "pydantic" in dep_map
    assert "pytest" in dep_map
    assert "requests" not in dep_map


def test_parse_package_json(tmp_path: Path) -> None:
    """Verify parsing Node.js package.json file."""
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text(
        """{
  "name": "my-app",
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "vite": "^5.1.0"
  }
}""",
        encoding="utf-8",
    )

    analyzer = DependencyAnalyzer()
    deps = analyzer.parse_package_json(pkg_file)

    dep_map = {d.name: d for d in deps}
    assert "react" in dep_map
    assert dep_map["react"].version_spec == "^18.2.0"
    assert dep_map["react"].is_dev is False
    assert "typescript" in dep_map
    assert dep_map["typescript"].is_dev is True


def test_parse_pyproject_toml(tmp_path: Path) -> None:
    """Verify parsing pyproject.toml PEP 621 dependencies."""
    toml_file = tmp_path / "pyproject.toml"
    toml_file.write_text(
        """[project]
name = "demo"
dependencies = [
    "typer>=0.12.0",
    "rich>=13.0.0",
]
""",
        encoding="utf-8",
    )

    analyzer = DependencyAnalyzer()
    deps = analyzer.parse_pyproject_toml(toml_file)

    dep_map = {d.name: d for d in deps}
    assert "typer" in dep_map
    assert "rich" in dep_map

