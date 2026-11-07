"""Architecture mapper analyzing module hierarchies, layers, entry points, and dependency flows."""

from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field

from codeagent.indexing.import_analyzer import ImportAnalyzer, ModuleDependencyGraph
from codeagent.indexing.symbol_extractor import ExtractedSymbol, SymbolExtractor
from codeagent.memory.memory_store import MemoryStore


class ProjectLayer(BaseModel):
    """Architectural layer grouping related files (e.g. presentation, domain, persistence)."""

    name: str  # "Presentation / CLI", "API / Controllers", "Domain / Services", "Data / Persistence", "Tests", "Config"
    description: str
    files: List[str] = Field(default_factory=list)

    @property
    def layer_type(self) -> str:
        """Normalized layer classification."""
        for t in ["CLI", "Presentation", "API", "Domain", "Data", "Tests", "Config"]:
            if t.lower() in self.name.lower():
                return t
        return self.name


class ArchitectureMap(BaseModel):
    """Structured architectural blueprint of a software project."""

    project_type: str = "Generic Project"
    architectural_pattern: str = "Modular Monolith"
    entry_points: List[str] = Field(default_factory=list)
    layers: List[ProjectLayer] = Field(default_factory=list)
    top_level_packages: List[str] = Field(default_factory=list)
    module_count: int = 0
    symbol_count: int = 0
    circular_dependencies: List[List[str]] = Field(default_factory=list)

    def to_summary(self) -> str:
        """Format an informative summary of project architecture."""
        lines = [
            f"Pattern: {self.architectural_pattern} ({self.project_type})",
            f"Entry Points: {', '.join(self.entry_points) if self.entry_points else 'None'}",
            f"Packages: {', '.join(self.top_level_packages) if self.top_level_packages else 'Root'}",
            f"Modules: {self.module_count} | Total Symbols: {self.symbol_count}",
        ]
        if self.circular_dependencies:
            lines.append(f"Circular Dependencies: {len(self.circular_dependencies)} cycles detected")
        for layer in self.layers:
            if layer.files:
                lines.append(f"  • {layer.name} ({len(layer.files)} files): {', '.join(layer.files[:4])}")
        return "\n".join(lines)


class ArchitectureMapper:
    """Discovers project structure, module relationships, and software architectural patterns."""

    def __init__(self, store: Optional[MemoryStore] = None) -> None:
        """Initialize ArchitectureMapper."""
        self.store = store
        self.import_analyzer = ImportAnalyzer()

    def build_architecture_map(
        self,
        workspace_root: Path,
        project_id: Optional[str] = None,
        known_entry_points: Optional[List[str]] = None,
        project_type: str = "Generic",
    ) -> ArchitectureMap:
        """Analyze project files and build a structured architecture map."""
        entry_points = known_entry_points or []
        files: List[str] = []

        # Fetch files from database if store is available, else scan workspace
        if self.store and project_id:
            rows = self.store.execute_query(
                "SELECT file_path FROM indexed_files WHERE project_id = ?;",
                (project_id,),
            )
            files = [r["file_path"] for r in rows]
        else:
            for p in workspace_root.rglob("*.py"):
                if not any(part.startswith((".", "__pycache__", ".venv", "venv")) for part in p.parts):
                    files.append(str(p.relative_to(workspace_root)).replace("\\", "/"))

        # 1. Discover top-level packages
        top_packages = self._find_top_level_packages(workspace_root, files)

        # 2. Categorize files into architectural layers
        layers = self._categorize_layers(files)

        # 3. Detect architectural pattern
        pattern = self._infer_pattern(files, layers, project_type)

        # 4. Count symbols if store available
        symbol_count = 0
        if self.store and project_id:
            s_row = self.store.execute_query_one(
                "SELECT COUNT(*) as cnt FROM code_symbols WHERE project_id = ?;",
                (project_id,),
            )
            symbol_count = s_row["cnt"] if s_row else 0

        return ArchitectureMap(
            project_type=project_type,
            architectural_pattern=pattern,
            entry_points=entry_points,
            layers=layers,
            top_level_packages=top_packages,
            module_count=len(files),
            symbol_count=symbol_count,
            circular_dependencies=[],
        )

    map_project = build_architecture_map

    def _find_top_level_packages(self, root: Path, files: List[str]) -> List[str]:
        """Identify primary top-level code directories."""
        packages: Set[str] = set()
        for f in files:
            parts = Path(f).parts
            if len(parts) > 1 and parts[0] not in ("tests", "docs", "scripts", ".codeagent"):
                packages.add(parts[0])
        return sorted(list(packages))

    def _categorize_layers(self, files: List[str]) -> List[ProjectLayer]:
        """Group project files into conventional software layers."""
        cli_files: List[str] = []
        api_files: List[str] = []
        domain_files: List[str] = []
        data_files: List[str] = []
        test_files: List[str] = []
        config_files: List[str] = []

        for f in files:
            f_low = f.lower()
            if "test" in f_low:
                test_files.append(f)
            elif any(k in f_low for k in ("cli", "console", "cmd", "main.py", "app.py")):
                cli_files.append(f)
            elif any(k in f_low for k in ("route", "api", "controller", "endpoint", "view")):
                api_files.append(f)
            elif any(k in f_low for k in ("db", "database", "model", "schema", "store", "storage", "repository")):
                data_files.append(f)
            elif any(k in f_low for k in ("config", "setting", "env")):
                config_files.append(f)
            else:
                domain_files.append(f)

        return [
            ProjectLayer(name="CLI / Entry Points", description="Console interfaces and main entry scripts", files=sorted(cli_files)),
            ProjectLayer(name="API / Controllers", description="HTTP endpoints and route handlers", files=sorted(api_files)),
            ProjectLayer(name="Domain / Business Logic", description="Core operations, engines, and domain models", files=sorted(domain_files)),
            ProjectLayer(name="Data / Storage", description="Database tables, repositories, and persistence", files=sorted(data_files)),
            ProjectLayer(name="Configuration", description="Application configuration and environment settings", files=sorted(config_files)),
            ProjectLayer(name="Tests", description="Unit and integration test suites", files=sorted(test_files)),
        ]

    def _infer_pattern(self, files: List[str], layers: List[ProjectLayer], project_type: str) -> str:
        """Infer high-level software pattern from structure."""
        if any(l.name == "API / Controllers" and l.files for l in layers):
            return "REST API / MVC Architecture"
        elif any("cli" in f.lower() for f in files) or "cli" in project_type.lower():
            return "Modular Command-Line Application"
        elif any("fastapi" in project_type.lower() for _ in [1]):
            return "FastAPI Asynchronous Microservice"
        elif any("flask" in project_type.lower() for _ in [1]):
            return "Flask Modular Web Application"
        elif any("react" in project_type.lower() for _ in [1]):
            return "Single Page Application (SPA)"
        return "Modular Monolith"
