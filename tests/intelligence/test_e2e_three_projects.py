"""End-to-end multi-project verification across three distinct real project structures:
1. Flask Web Application (Python / Flask)
2. React & TypeScript Application (Node.js / React / Vite)
3. Python AI Engine Application (Python / PyTorch / Ollama / Pyproject)
"""

from pathlib import Path
import pytest

from codeagent.config.settings import Settings
from codeagent.memory.memory_manager import MemoryManager
from codeagent.intelligence.project_manager import ProjectManager


@pytest.fixture
def three_projects_environment(tmp_path: Path) -> tuple[ProjectManager, Path, Path, Path]:
    """Create three distinct realistic application projects on disk."""
    data_dir = tmp_path / "agent_data"

    # 1. Flask Web Project
    flask_dir = tmp_path / "flask_ecommerce"
    flask_dir.mkdir()
    (flask_dir / "app.py").write_text(
        """from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'flask_ecommerce'})

@app.route('/products')
def list_products():
    return jsonify([{'id': 1, 'name': 'Laptop'}])

if __name__ == '__main__':
    app.run(port=5000)
""",
        encoding="utf-8",
    )
    (flask_dir / "requirements.txt").write_text("flask>=3.0.0\ngunicorn>=21.0.0\npytest>=8.0.0\n", encoding="utf-8")
    (flask_dir / "Dockerfile").write_text("FROM python:3.12-slim\nCMD [\"gunicorn\", \"app:app\"]\n", encoding="utf-8")

    # 2. React / TypeScript Frontend Project
    react_dir = tmp_path / "react_dashboard"
    react_dir.mkdir()
    (react_dir / "package.json").write_text(
        """{
  "name": "react-admin-dashboard",
  "version": "1.0.0",
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "lucide-react": "^0.300.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}""",
        encoding="utf-8",
    )
    src_dir = react_dir / "src"
    src_dir.mkdir()
    (src_dir / "App.tsx").write_text(
        """import React from 'react';

export function DashboardHeader({ title }: { title: string }) {
    return <header><h1>{title}</h1></header>;
}

export default function App() {
    return <DashboardHeader title="Admin Portal" />;
}
""",
        encoding="utf-8",
    )
    (react_dir / "vite.config.ts").write_text("import { defineConfig } from 'vite';\nexport default defineConfig({});\n", encoding="utf-8")

    # 3. Python AI Engine Project
    ai_dir = tmp_path / "ai_inference_engine"
    ai_dir.mkdir()
    (ai_dir / "pyproject.toml").write_text(
        """[project]
name = "ai-inference-engine"
version = "0.2.0"
dependencies = [
    "torch>=2.2.0",
    "ollama>=0.3.0",
    "numpy>=1.26.0",
]
""",
        encoding="utf-8",
    )
    ai_src = ai_dir / "engine"
    ai_src.mkdir()
    (ai_src / "pipeline.py").write_text(
        """import torch
import ollama

class InferencePipeline:
    def __init__(self, model_name: str = "qwen3:latest"):
        self.model = model_name

    def generate_embeddings(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]
""",
        encoding="utf-8",
    )

    cfg = Settings(project_data_path=str(data_dir))
    mm = MemoryManager(settings=cfg)
    pm = ProjectManager(memory_manager=mm, settings=cfg)

    return pm, flask_dir, react_dir, ai_dir


def test_e2e_three_project_intelligence_and_isolation(
    three_projects_environment: tuple[ProjectManager, Path, Path, Path],
) -> None:
    """Verify registration, deep analysis, indexing, search, memory persistence, and isolation across 3 projects."""
    pm, flask_dir, react_dir, ai_dir = three_projects_environment

    # --- PROJECT 1: Flask Web App ---
    rec_flask = pm.register_project(flask_dir, name="FlaskEcommerce", set_active=True)
    assert pm.active_project_id == rec_flask.id

    # 1.1 Analyze Flask project
    flask_analysis = pm.analyze_active_project()
    assert flask_analysis.project_type == "Flask Web Application"
    assert "Flask" in flask_analysis.frameworks
    assert "requirements.txt" in flask_analysis.dependency_files
    assert "Dockerfile" in flask_analysis.deployment_configs

    # 1.2 Index Flask project
    flask_idx_status = pm.index_active_project(rebuild=True)
    assert flask_idx_status.files_indexed >= 1
    assert flask_idx_status.total_symbols >= 2

    # 1.3 Search Flask symbols
    flask_symbols = pm.search_active_project("health_check", search_type="symbol")
    assert len(flask_symbols) >= 1
    assert "health_check" in (flask_symbols[0].matched_content or "")

    # 1.4 Store Flask memory
    pm.memory_manager.store_fact(rec_flask.id, "architecture", "port", "Runs on port 5000 with Gunicorn")

    # --- PROJECT 2: React Dashboard ---
    rec_react = pm.register_project(react_dir, name="ReactDashboard", set_active=True)
    assert pm.active_project_id == rec_react.id

    # 2.1 Analyze React project
    react_analysis = pm.analyze_active_project()
    assert "React" in react_analysis.frameworks
    assert "Vite" in react_analysis.build_systems

    # 2.2 Index React project
    react_idx_status = pm.index_active_project(rebuild=True)
    assert react_idx_status.files_indexed >= 2

    # 2.3 Search React symbols
    react_symbols = pm.search_active_project("DashboardHeader", search_type="symbol")
    assert len(react_symbols) >= 1

    # 2.4 Store React memory
    pm.memory_manager.store_fact(rec_react.id, "architecture", "ui_library", "React 18 with Lucide icons")

    # --- PROJECT 3: AI Inference Engine ---
    rec_ai = pm.register_project(ai_dir, name="AIEngine", set_active=True)
    assert pm.active_project_id == rec_ai.id

    # 3.1 Analyze AI project
    ai_analysis = pm.analyze_active_project()
    assert "PyTorch" in ai_analysis.frameworks
    assert "pyproject.toml" in ai_analysis.dependency_files

    # 3.2 Index AI project
    ai_idx_status = pm.index_active_project(rebuild=True)
    assert ai_idx_status.files_indexed >= 1
    assert ai_idx_status.total_symbols >= 1

    # 3.3 Search AI symbols
    ai_symbols = pm.search_active_project("InferencePipeline", search_type="symbol")
    assert len(ai_symbols) >= 1

    # 3.4 Store AI memory
    pm.memory_manager.store_fact(rec_ai.id, "stack", "primary_model", "Qwen3 local model via Ollama")

    # --- VERIFY ABSOLUTE PROJECT ISOLATION ---
    # Switch back to Flask
    pm.switch_project("FlaskEcommerce")
    assert pm.active_project_id == rec_flask.id

    # Flask facts should NOT include React or AI facts
    flask_facts = pm.memory_manager.list_facts(rec_flask.id)
    assert len(flask_facts) == 1
    assert "Runs on port 5000" in flask_facts[0].value
    assert "React" not in flask_facts[0].value
    assert "Qwen3" not in flask_facts[0].value

    # Flask search should NOT find React or AI symbols
    flask_leak_check = pm.search_active_project("DashboardHeader", search_type="symbol")
    assert len(flask_leak_check) == 0

    # Switch to React
    pm.switch_project("ReactDashboard")
    react_facts = pm.memory_manager.list_facts(rec_react.id)
    assert len(react_facts) == 1
    assert "Lucide icons" in react_facts[0].value
    assert "port 5000" not in react_facts[0].value

    # Context bundle for React should contain only React knowledge
    react_context = pm.build_active_context(user_query="What UI library?")
    prompt_text = react_context.to_prompt_context()
    assert "React 18 with Lucide icons" in prompt_text
    assert "Gunicorn" not in prompt_text
