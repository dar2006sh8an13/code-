"""Project structure analysis engine identifying frameworks, dependencies, and entry points."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Optional, Union

from codeagent.filesystem.path_validator import PathValidator
from codeagent.filesystem.scanner import DirectoryScanner


@dataclass
class ProjectAnalysis:
    """Detailed structural findings of a scanned project."""

    project_type: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    dependency_files: list[str] = field(default_factory=list)
    configuration_files: list[str] = field(default_factory=list)
    important_directories: list[str] = field(default_factory=list)
    total_files: int = 0
    total_dirs: int = 0
    summary: str = ""

    def to_summary(self) -> str:
        """Format an informative summary of project analysis."""
        lines = [
            f"Project Type: {self.project_type}",
            f"Languages: {', '.join(self.languages) if self.languages else 'None detected'}",
            f"Frameworks / Libraries: {', '.join(self.frameworks) if self.frameworks else 'None detected'}",
            f"Entry Points: {', '.join(self.entry_points) if self.entry_points else 'None detected'}",
            f"Dependency Files: {', '.join(self.dependency_files) if self.dependency_files else 'None'}",
            f"Config Files: {', '.join(self.configuration_files) if self.configuration_files else 'None'}",
            f"Key Directories: {', '.join(self.important_directories) if self.important_directories else 'None'}",
        ]
        return "\n".join(lines)


# Known configuration and dependency filenames
DEPENDENCY_FILENAMES = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "Pipfile", "poetry.lock", "package.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "Gemfile", "Cargo.toml", "go.mod",
}

CONFIG_FILENAMES = {
    ".gitignore", ".editorconfig", "tsconfig.json", "jsconfig.json",
    "vite.config.js", "vite.config.ts", "webpack.config.js", "next.config.js",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "pytest.ini", "tox.ini", ".env.example", "ruff.toml", ".eslintrc",
}

ENTRY_POINT_FILENAMES = {
    "main.py", "app.py", "cli.py", "__main__.py", "server.py", "manage.py",
    "wsgi.py", "asgi.py", "run.py", "index.js", "index.ts", "server.js",
    "app.js", "src/main.py", "src/app.py", "src/index.js", "src/index.ts",
    "src/index.tsx", "src/main.tsx", "src/App.tsx", "index.html",
}

IMPORTANT_DIR_NAMES = {
    "src", "app", "lib", "tests", "test", "docs", "components", "pages",
    "static", "templates", "public", "api", "routes", "models", "views",
    "controllers", "services", "utils", "codeagent",
}

LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React JSX)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React TSX)",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".sh": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
}


class ProjectAnalyzer:
    """Inspects project files, dependencies, entry points, and detects frameworks."""

    def __init__(
        self,
        validator: Optional[PathValidator] = None,
        scanner: Optional[DirectoryScanner] = None,
    ) -> None:
        """Initialize ProjectAnalyzer."""
        self.validator = validator or PathValidator()
        self.scanner = scanner or DirectoryScanner(validator=self.validator)

    def analyze(self, target_path: Optional[Union[str, Path]] = None) -> ProjectAnalysis:
        """Analyze project directory structure, dependencies, and detect frameworks.

        Args:
            target_path: Root of project to analyze (defaults to workspace root).

        Returns:
            ProjectAnalysis: Detailed structural and framework findings.
        """
        resolved_path = self.validator.validate_and_resolve(
            target_path or self.validator.workspace_root,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        scan_res = self.scanner.scan_tree(resolved_path, max_depth=5)

        discovered_deps: list[str] = []
        discovered_configs: list[str] = []
        discovered_entry_points: list[str] = []
        discovered_dirs: list[str] = []
        languages_detected: set[str] = set()
        frameworks_detected: set[str] = set()

        # 1. Identify files and directories from scan
        for entry in scan_res.entries:
            name_lower = entry.name.lower()
            rel_norm = entry.relative_path.replace("\\", "/")

            if entry.is_dir:
                if name_lower in IMPORTANT_DIR_NAMES:
                    discovered_dirs.append(entry.relative_path)
            else:
                # Languages
                if entry.extension in LANGUAGE_BY_EXT:
                    languages_detected.add(LANGUAGE_BY_EXT[entry.extension])

                # Dependencies
                if name_lower in DEPENDENCY_FILENAMES:
                    discovered_deps.append(entry.relative_path)

                # Configurations
                if name_lower in CONFIG_FILENAMES or name_lower.startswith(".env"):
                    discovered_configs.append(entry.relative_path)

                # Entry points
                if name_lower in ENTRY_POINT_FILENAMES or rel_norm in ENTRY_POINT_FILENAMES:
                    discovered_entry_points.append(entry.relative_path)

        # 2. Inspect dependency files for specific frameworks
        for dep_rel in discovered_deps:
            full_dep_path = resolved_path / dep_rel
            if not full_dep_path.exists() or not full_dep_path.is_file():
                continue

            try:
                if full_dep_path.name == "package.json":
                    with open(full_dep_path, "r", encoding="utf-8") as f:
                        pkg_data = json.load(f)
                    all_deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                    if "react" in all_deps:
                        frameworks_detected.add("React")
                    if "next" in all_deps:
                        frameworks_detected.add("Next.js")
                    if "vue" in all_deps:
                        frameworks_detected.add("Vue")
                    if "express" in all_deps:
                        frameworks_detected.add("Express")
                    if "fastify" in all_deps:
                        frameworks_detected.add("Fastify")
                    if "tailwindcss" in all_deps:
                        frameworks_detected.add("Tailwind CSS")

                elif full_dep_path.name in ("pyproject.toml", "requirements.txt", "Pipfile"):
                    with open(full_dep_path, "r", encoding="utf-8", errors="ignore") as f:
                        content_lower = f.read().lower()
                    if "fastapi" in content_lower:
                        frameworks_detected.add("FastAPI")
                    if "django" in content_lower:
                        frameworks_detected.add("Django")
                    if "flask" in content_lower:
                        frameworks_detected.add("Flask")
                    if "typer" in content_lower:
                        frameworks_detected.add("Typer")
                    if "pydantic" in content_lower:
                        frameworks_detected.add("Pydantic")
                    if "pytest" in content_lower:
                        frameworks_detected.add("Pytest")
            except Exception:
                continue

        # Check for Django manage.py
        if any("manage.py" in ep.lower() for ep in discovered_entry_points):
            frameworks_detected.add("Django")

        # 3. Determine high-level project type
        project_type = "Generic / Unknown"
        if "FastAPI" in frameworks_detected:
            project_type = "Python (FastAPI Web Application)"
        elif "Django" in frameworks_detected:
            project_type = "Python (Django Web Application)"
        elif "Flask" in frameworks_detected:
            project_type = "Python (Flask Web Application)"
        elif "React" in frameworks_detected:
            project_type = "React / Frontend Web Application"
        elif "Next.js" in frameworks_detected:
            project_type = "Next.js Fullstack Web Application"
        elif "Express" in frameworks_detected or "Node.js" in languages_detected or any("package.json" in d for d in discovered_deps):
            project_type = "Node.js Application"
        elif "Python" in languages_detected:
            project_type = "Python Application"
        elif "HTML" in languages_detected or "JavaScript" in languages_detected:
            project_type = "HTML / CSS / JavaScript Web Project"

        sorted_languages = sorted(languages_detected)
        sorted_frameworks = sorted(frameworks_detected)

        analysis = ProjectAnalysis(
            project_type=project_type,
            languages=sorted_languages,
            frameworks=sorted_frameworks,
            entry_points=discovered_entry_points,
            dependency_files=discovered_deps,
            configuration_files=discovered_configs,
            important_directories=discovered_dirs,
            total_files=scan_res.total_files,
            total_dirs=scan_res.total_dirs,
        )
        analysis.summary = analysis.to_summary()
        return analysis

