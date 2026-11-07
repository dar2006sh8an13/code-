"""Multi-project workspace manager registering projects, switching contexts, and ensuring isolation."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field

from codeagent.config.settings import Settings, get_settings
from codeagent.indexing.indexer import IndexStatus, ProjectIndexer
from codeagent.indexing.search_engine import SearchEngine
from codeagent.indexing.vector_search import VectorSearchEngine
from codeagent.intelligence.context_builder import ContextBuilder, ProjectContextBundle
from codeagent.intelligence.project_analyzer import ComprehensiveProjectAnalysis, ProjectAnalyzer
from codeagent.memory.memory_manager import MemoryManager, ProjectFact


class ProjectRecord(BaseModel):
    """Metadata record for a registered project workspace."""

    id: str
    name: str
    path: str
    created_at: str
    updated_at: str
    is_active: bool = False

    def to_summary(self) -> str:
        """Format an informative summary of this project record."""
        active_str = " [ACTIVE]" if self.is_active else ""
        return f"{self.name} (ID: {self.id}){active_str} -> {self.path}"


class ProjectManager:
    """Coordinates multi-project workspaces, indexing, memory, and context isolation."""

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize ProjectManager."""
        self.settings = settings or get_settings()
        self.memory_manager = memory_manager or MemoryManager(settings=self.settings)
        self.store = self.memory_manager.store

        self.search_engine = SearchEngine(store=self.store)
        self.vector_search = VectorSearchEngine(store=self.store, enabled=self.settings.semantic_search_enabled)
        self.project_analyzer = ProjectAnalyzer()
        self.context_builder = ContextBuilder(
            memory_manager=self.memory_manager,
            search_engine=self.search_engine,
        )

        # Active project tracking
        self._active_project_id: Optional[str] = None
        self._active_workspace_path: Optional[Path] = None
        self._load_active_project()

    @property
    def active_project_id(self) -> str:
        """Return currently active project ID, or create default workspace project if none active."""
        if not self._active_project_id:
            # Register or activate current working directory by default
            cwd = Path.cwd().resolve()
            proj = self.register_project(path=cwd, name=cwd.name, set_active=True)
            self._active_project_id = proj.id
            self._active_workspace_path = cwd
        return self._active_project_id

    @property
    def active_workspace_path(self) -> Path:
        """Return Path to currently active workspace root."""
        if not self._active_workspace_path:
            _ = self.active_project_id  # Ensures initialized
        return self._active_workspace_path or Path.cwd().resolve()

    def register_project(
        self,
        path: Union[str, Path],
        name: Optional[str] = None,
        set_active: bool = True,
    ) -> ProjectRecord:
        """Register a project directory workspace and assign a deterministic unique ID."""
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Project directory does not exist: '{resolved}'")
        if not resolved.is_dir():
            raise ValueError(f"Specified path is not a directory: '{resolved}'")

        # Deterministic project ID based on canonical path hash
        path_str = str(resolved).replace("\\", "/")
        proj_id = hashlib.sha256(path_str.encode("utf-8")).hexdigest()[:12]
        proj_name = name or resolved.name or f"project_{proj_id}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check existing
        row = self.store.execute_query_one(
            "SELECT * FROM projects WHERE id = ? OR path = ?;",
            (proj_id, path_str),
        )

        if row:
            rec = ProjectRecord(**dict(row))
            if set_active:
                self.switch_project(rec.id)
            return rec

        # Insert new record
        self.store.execute_write(
            """
            INSERT INTO projects (id, name, path, created_at, updated_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (proj_id, proj_name, path_str, now_iso, now_iso, 1 if set_active else 0),
        )

        rec = ProjectRecord(
            id=proj_id,
            name=proj_name,
            path=path_str,
            created_at=now_iso,
            updated_at=now_iso,
            is_active=set_active,
        )

        if set_active:
            self._set_active_record(rec)

        return rec

    def list_projects(self) -> List[ProjectRecord]:
        """List all registered projects."""
        rows = self.store.execute_query("SELECT * FROM projects ORDER BY updated_at DESC;")
        return [ProjectRecord(**dict(r)) for r in rows]

    def switch_project(self, identifier: str) -> ProjectRecord:
        """Switch active project context by ID, name, or path."""
        # Find project
        row = self.store.execute_query_one(
            "SELECT * FROM projects WHERE id = ? OR name = ? OR path = ?;",
            (identifier, identifier, identifier),
        )
        if not row:
            # Check prefix match on ID
            row = self.store.execute_query_one(
                "SELECT * FROM projects WHERE id LIKE ? LIMIT 1;",
                (f"{identifier}%",),
            )

        if not row:
            raise ValueError(f"Project '{identifier}' not found among registered projects.")

        rec = ProjectRecord(**dict(row))
        self._set_active_record(rec)
        return rec

    def get_project_info(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Get overview info and stats for a project."""
        p_id = project_id or self.active_project_id
        row = self.store.execute_query_one("SELECT * FROM projects WHERE id = ?;", (p_id,))
        if not row:
            raise ValueError(f"Project '{p_id}' not found.")

        rec = ProjectRecord(**dict(row))
        indexer = ProjectIndexer(store=self.store, workspace_root=Path(rec.path))
        status = indexer.get_status(p_id)
        facts = self.memory_manager.list_facts(project_id=p_id, limit=50)

        return {
            "project": rec,
            "index_status": status,
            "facts_count": len(facts),
            "facts": facts,
        }

    def analyze_active_project(self) -> ComprehensiveProjectAnalysis:
        """Run deep project analysis on active workspace."""
        return self.project_analyzer.analyze(self.active_workspace_path)

    def index_active_project(self, rebuild: bool = False) -> IndexStatus:
        """Index or re-index active workspace files into SQLite."""
        indexer = ProjectIndexer(
            store=self.store,
            settings=self.settings,
            workspace_root=self.active_workspace_path,
        )
        return indexer.index_project(project_id=self.active_project_id, rebuild=rebuild)

    def search_active_project(
        self,
        query: str,
        search_type: str = "text",  # "text", "symbol", "file", "semantic"
        limit: int = 15,
    ) -> List[Any]:
        """Search across active project index."""
        p_id = self.active_project_id
        if search_type == "symbol":
            return self.search_engine.search_symbol(project_id=p_id, name=query, limit=limit)
        elif search_type == "file":
            return self.search_engine.search_filename(project_id=p_id, pattern=query, limit=limit)
        elif search_type == "semantic":
            return self.vector_search.search_semantic(project_id=p_id, query=query, limit=limit)
        else:
            return self.search_engine.search_exact_text(project_id=p_id, query=query, limit=limit)

    def build_active_context(self, user_query: Optional[str] = None) -> ProjectContextBundle:
        """Synthesize project context bundle for active project."""
        return self.context_builder.build_context(
            project_id=self.active_project_id,
            workspace_root=self.active_workspace_path,
            user_query=user_query,
        )

    def _set_active_record(self, record: ProjectRecord) -> None:
        """Update active project in DB and in-memory state."""
        self.store.execute_write("UPDATE projects SET is_active = 0;")
        self.store.execute_write(
            "UPDATE projects SET is_active = 1, updated_at = ? WHERE id = ?;",
            (datetime.now(timezone.utc).isoformat(), record.id),
        )
        self._active_project_id = record.id
        self._active_workspace_path = Path(record.path)

    def _load_active_project(self) -> None:
        """Load currently marked active project from database if present."""
        row = self.store.execute_query_one("SELECT * FROM projects WHERE is_active = 1 LIMIT 1;")
        if row:
            self._active_project_id = row["id"]
            self._active_workspace_path = Path(row["path"])
