"""Comprehensive software project analyzer evaluating frameworks, build systems, and entry points."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field

from codeagent.intelligence.dependency_analyzer import DependencyAnalyzer, DependencyReport
from codeagent.intelligence.language_detector import LanguageDetector, LanguageDistribution


class ComprehensiveProjectAnalysis(BaseModel):
    """Exhaustive structural and technical findings for a project workspace."""

    project_type: str
    primary_language: str
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    entry_points: List[str] = Field(default_factory=list)
    important_source_files: List[str] = Field(default_factory=list)
    directory_structure: List[str] = Field(default_factory=list)
    configuration_files: List[str] = Field(default_factory=list)
    dependency_files: List[str] = Field(default_factory=list)
    test_directories: List[str] = Field(default_factory=list)
    build_systems: List[str] = Field(default_factory=list)
    deployment_configs: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    total_files: int = 0
    total_dirs: int = 0

    def to_summary(self) -> str:
        """Format an informative summary of project analysis."""
        lines = [
            f"Project Type: {self.project_type} (Primary: {self.primary_language})",
            f"Languages: {', '.join(self.languages) if self.languages else 'None'}",
            f"Frameworks / Libraries: {', '.join(self.frameworks) if self.frameworks else 'None'}",
            f"Entry Points: {', '.join(self.entry_points) if self.entry_points else 'None'}",
            f"Build Systems: {', '.join(self.build_systems) if self.build_systems else 'None'}",
            f"Deployment: {', '.join(self.deployment_configs) if self.deployment_configs else 'None'}",
            f"Dependency Manifests: {', '.join(self.dependency_files) if self.dependency_files else 'None'}",
            f"Config Files: {', '.join(self.configuration_files) if self.configuration_files else 'None'}",
            f"Test Directories: {', '.join(self.test_directories) if self.test_directories else 'None'}",
        ]
        return "\n".join(lines)


class ProjectAnalyzer:
    """Evaluates software workspaces across Python, JavaScript, TypeScript, Java, and C/C++ stacks."""

    def __init__(self) -> None:
        """Initialize ProjectAnalyzer."""
        self.lang_detector = LanguageDetector()
        self.dep_analyzer = DependencyAnalyzer()

    def analyze(self, workspace_root: Path) -> ComprehensiveProjectAnalysis:
        """Perform comprehensive inspection of the workspace."""
        root = workspace_root.resolve()

        # 1. Detect languages
        lang_dist = self.lang_detector.detect_languages(root)
        primary_lang = lang_dist.primary_language
        langs = [l.name for l in lang_dist.languages]

        # 2. Analyze dependencies
        dep_report = self.dep_analyzer.analyze_workspace(root)
        dep_names = [d.name.lower() for d in dep_report.dependencies]

        # 3. Scan workspace structure
        entry_points: List[str] = []
        important_files: List[str] = []
        dir_structure: List[str] = []
        config_files: List[str] = []
        test_dirs: List[str] = []
        build_systems: List[str] = []
        deployment_configs: List[str] = []

        total_files = 0
        total_dirs = 0

        excluded_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".codeagent"}

        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith(".")]
            total_dirs += len(dirs)
            total_files += len(files)

            rel_r = str(Path(r).relative_to(root)).replace("\\", "/")
            if rel_r != "." and rel_r not in dir_structure and len(dir_structure) < 20:
                dir_structure.append(rel_r)

            # Check test dirs
            for d in dirs:
                if d.lower() in ("test", "tests", "spec", "specs", "__tests__"):
                    rel_d = str((Path(r) / d).relative_to(root)).replace("\\", "/")
                    if rel_d not in test_dirs:
                        test_dirs.append(rel_d)

            for f in files:
                rel_f = str((Path(r) / f).relative_to(root)).replace("\\", "/")

                # Entry points
                if f.lower() in ("main.py", "app.py", "cli.py", "__main__.py", "server.py", "manage.py", "index.js", "index.ts", "server.js", "app.js", "index.html"):
                    if rel_f not in entry_points:
                        entry_points.append(rel_f)

                # Configurations
                if f in (".gitignore", ".editorconfig", "tsconfig.json", "jsconfig.json", "vite.config.js", "vite.config.ts", "webpack.config.js", "pytest.ini", "tox.ini", "ruff.toml"):
                    if rel_f not in config_files:
                        config_files.append(rel_f)

                # Build systems
                if f in ("pyproject.toml", "setup.py", "package.json", "pom.xml", "build.gradle", "CMakeLists.txt", "Makefile"):
                    build_name = f
                    if f == "CMakeLists.txt":
                        build_name = "CMake"
                    elif f == "Makefile":
                        build_name = "Make"
                    elif f == "pom.xml":
                        build_name = "Maven"
                    elif f == "build.gradle":
                        build_name = "Gradle"
                    elif f == "package.json":
                        build_name = "npm / Node.js"
                    elif f in ("pyproject.toml", "setup.py"):
                        build_name = "Python Setuptools / Flit / Poetry"

                    if build_name not in build_systems:
                        build_systems.append(build_name)

                # Vite / Webpack build tool configs
                if f.startswith("vite.config."):
                    if "Vite" not in build_systems:
                        build_systems.append("Vite")
                elif f.startswith("webpack.config."):
                    if "Webpack" not in build_systems:
                        build_systems.append("Webpack")

                # Deployment configs
                if f == "Dockerfile" or f.startswith("docker-compose"):
                    if "Docker" not in deployment_configs:
                        deployment_configs.append("Docker")
                    if rel_f not in deployment_configs:
                        deployment_configs.append(rel_f)
                elif f == "Procfile":
                    if "Procfile" not in deployment_configs:
                        deployment_configs.append("Procfile")
                    if rel_f not in deployment_configs:
                        deployment_configs.append(rel_f)
                elif f in ("render.yaml", "vercel.json", "netlify.toml"):
                    platform = f.split(".")[0].capitalize()
                    if platform not in deployment_configs:
                        deployment_configs.append(platform)
                    if rel_f not in deployment_configs:
                        deployment_configs.append(rel_f)

                # Important files sample
                if len(important_files) < 15 and Path(f).suffix.lower() in (".py", ".js", ".ts", ".java", ".c", ".cpp"):
                    important_files.append(rel_f)

        # 4. Detect frameworks from dependency names and files
        frameworks: List[str] = []

        if "fastapi" in dep_names:
            frameworks.append("FastAPI")
        if "flask" in dep_names:
            frameworks.append("Flask")
        if "django" in dep_names:
            frameworks.append("Django")
        if "react" in dep_names or any(f.endswith((".jsx", ".tsx")) for f in important_files):
            frameworks.append("React")
        if "express" in dep_names:
            frameworks.append("Express.js")
        if "next" in dep_names:
            frameworks.append("Next.js")
        if "vue" in dep_names:
            frameworks.append("Vue.js")
        if "torch" in dep_names or "pytorch" in dep_names:
            frameworks.append("PyTorch")
        if "tensorflow" in dep_names:
            frameworks.append("TensorFlow")
        if "ollama" in dep_names:
            frameworks.append("Ollama LLM SDK")
        if "typer" in dep_names:
            frameworks.append("Typer CLI")
        if "pytest" in dep_names:
            frameworks.append("pytest")
        if "spring" in " ".join(dep_names) or (root / "pom.xml").exists():
            if any("spring" in d for d in dep_names):
                frameworks.append("Spring Boot")

        # 5. Determine high-level project type
        project_type = self._determine_project_type(primary_lang, frameworks, build_systems)

        return ComprehensiveProjectAnalysis(
            project_type=project_type,
            primary_language=primary_lang,
            languages=langs,
            frameworks=frameworks,
            entry_points=entry_points,
            important_source_files=important_files,
            directory_structure=sorted(dir_structure),
            configuration_files=sorted(config_files),
            dependency_files=sorted(dep_report.manifest_files),
            test_directories=sorted(test_dirs),
            build_systems=sorted(build_systems),
            deployment_configs=sorted(deployment_configs),
            dependencies=[f"{d.name} ({d.version_spec or 'any'})" for d in dep_report.dependencies[:20]],
            total_files=total_files,
            total_dirs=total_dirs,
        )

    def _determine_project_type(self, primary_lang: str, frameworks: List[str], build_systems: List[str]) -> str:
        """Infer human-readable project classification."""
        if "FastAPI" in frameworks:
            return "FastAPI Web Application"
        elif "Flask" in frameworks:
            return "Flask Web Application"
        elif "Django" in frameworks:
            return "Django Web Application"
        elif "React" in frameworks and "Express.js" in frameworks:
            return "Full-Stack Node.js & React Project"
        elif "React" in frameworks:
            return "React Frontend Application"
        elif "Express.js" in frameworks or "npm / Node.js" in build_systems:
            return "Node.js Application"
        elif "PyTorch" in frameworks or "TensorFlow" in frameworks or "Ollama LLM SDK" in frameworks:
            return "Python AI / Machine Learning Project"
        elif primary_lang == "Python":
            return "Python Project"
        elif primary_lang in ("JavaScript", "TypeScript"):
            return "JavaScript / TypeScript Project"
        elif primary_lang == "Java":
            return "Java Application"
        elif primary_lang in ("C", "C++"):
            return "C / C++ Software Project"
        return "Software Development Project"
