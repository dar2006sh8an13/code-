"""Local code indexer orchestrating file traversal, chunking, symbol extraction, and database persistence."""

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Union
import uuid
from pydantic import BaseModel, Field

from codeagent.config.settings import Settings, get_settings
from codeagent.filesystem.path_validator import PathValidator, SENSITIVE_FILENAMES
from codeagent.indexing.chunker import CodeChunker
from codeagent.indexing.file_watcher import FileChangeSet, FileWatcher
from codeagent.indexing.import_analyzer import ImportAnalyzer, ImportRelation
from codeagent.indexing.symbol_extractor import SymbolExtractor
from codeagent.memory.memory_store import MemoryStore


class IndexStatus(BaseModel):
    """Statistics report on project index coverage."""

    project_id: str
    total_files_indexed: int
    total_symbols_indexed: int
    total_chunks_indexed: int
    total_imports_indexed: int
    files_indexed: int = 0
    duration_seconds: float = 0.0
    last_indexed_at: Optional[str] = None
    is_up_to_date: bool = True

    @property
    def total_symbols(self) -> int:
        return self.total_symbols_indexed

    @property
    def total_chunks(self) -> int:
        return self.total_chunks_indexed

    @property
    def total_imports(self) -> int:
        return self.total_imports_indexed

    def to_summary(self) -> str:
        """Format an informative summary of index state."""
        return (
            f"Files Indexed: {self.total_files_indexed}\n"
            f"Symbols:       {self.total_symbols_indexed}\n"
            f"Code Chunks:   {self.total_chunks_indexed}\n"
            f"Imports:       {self.total_imports_indexed}\n"
            f"Last Indexed:  {self.last_indexed_at or 'Never'}"
        )


class ProjectIndexer:
    """Indexes source code files into SQLite tables with incremental sync and full rebuild options."""

    SUPPORTED_EXTENSIONS = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".c",
        ".cpp",
        ".cc",
        ".h",
        ".hpp",
        ".html",
        ".css",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".md",
        ".sql",
        ".sh",
        ".bat",
        ".ps1",
    }

    def __init__(
        self,
        store: MemoryStore,
        settings: Optional[Settings] = None,
        workspace_root: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize ProjectIndexer."""
        self.store = store
        self.settings = settings or get_settings()
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.validator = PathValidator(workspace_root=self.workspace_root)

        excluded_list = [d.strip() for d in self.settings.index_excluded_dirs.split(",") if d.strip()]
        self.excluded_dirs = set(excluded_list) | {".git", ".codeagent", ".venv", "venv", "node_modules", "__pycache__"}

        self.symbol_extractor = SymbolExtractor()
        self.chunker = CodeChunker(
            target_chunk_size=self.settings.index_chunk_size,
            overlap_chars=self.settings.index_overlap,
        )
        self.import_analyzer = ImportAnalyzer()
        self.file_watcher = FileWatcher(
            workspace_root=self.workspace_root,
            excluded_dirs=self.excluded_dirs,
            max_file_size_mb=self.settings.max_index_file_size_mb,
        )

    def get_status(self, project_id: str) -> IndexStatus:
        """Retrieve current indexing counts and metrics for a project."""
        f_row = self.store.execute_query_one(
            "SELECT COUNT(*) as cnt, MAX(indexed_at) as last_idx FROM indexed_files WHERE project_id = ?;",
            (project_id,),
        )
        s_row = self.store.execute_query_one(
            "SELECT COUNT(*) as cnt FROM code_symbols WHERE project_id = ?;",
            (project_id,),
        )
        c_row = self.store.execute_query_one(
            "SELECT COUNT(*) as cnt FROM code_chunks WHERE project_id = ?;",
            (project_id,),
        )
        i_row = self.store.execute_query_one(
            "SELECT COUNT(*) as cnt FROM import_relationships WHERE project_id = ?;",
            (project_id,),
        )

        f_cnt = f_row["cnt"] if f_row else 0
        return IndexStatus(
            project_id=project_id,
            total_files_indexed=f_cnt,
            total_symbols_indexed=s_row["cnt"] if s_row else 0,
            total_chunks_indexed=c_row["cnt"] if c_row else 0,
            total_imports_indexed=i_row["cnt"] if i_row else 0,
            files_indexed=f_cnt,
            last_indexed_at=f_row["last_idx"] if f_row else None,
            is_up_to_date=True,
        )

    def index_project(self, project_id: str, rebuild: bool = False) -> IndexStatus:
        """Scan workspace and index source files. Supports incremental sync or full rebuild."""
        import time
        start_t = time.time()
        indexed_count = 0

        if rebuild:
            self._clear_project_index(project_id)

        changes = self.file_watcher.detect_changes(update_snapshot=True)

        if rebuild or not self._has_any_index(project_id):
            # Index all files found in workspace
            all_files = self._collect_indexable_files()
            for rel_path in all_files:
                self._index_file(project_id, rel_path)
                indexed_count += 1
        else:
            # Incremental updates
            for deleted_rel in changes.deleted_files:
                self._remove_file_from_index(project_id, deleted_rel)

            for modified_rel in changes.modified_files:
                self._remove_file_from_index(project_id, modified_rel)
                self._index_file(project_id, modified_rel)
                indexed_count += 1

            for created_rel in changes.created_files:
                self._index_file(project_id, created_rel)
                indexed_count += 1

        status = self.get_status(project_id)
        status.files_indexed = indexed_count
        status.duration_seconds = round(time.time() - start_t, 3)
        return status

    def _collect_indexable_files(self) -> List[str]:
        """Walk workspace and find all supported, non-sensitive, non-excluded files."""
        collected: List[str] = []
        max_bytes = self.settings.max_index_file_size_mb * 1024 * 1024

        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in self.excluded_dirs and not d.startswith(".")]

            for fname in files:
                if fname in SENSITIVE_FILENAMES or fname.startswith(".env") or fname.endswith((".pyc", ".pyd")):
                    continue

                full_p = Path(root) / fname
                ext = full_p.suffix.lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue

                try:
                    stat = full_p.stat()
                    if stat.st_size > max_bytes or stat.st_size == 0:
                        continue
                    rel_p = str(full_p.relative_to(self.workspace_root)).replace("\\", "/")
                    collected.append(rel_p)
                except (OSError, PermissionError):
                    continue

                if len(collected) >= self.settings.max_index_files:
                    break

        return collected

    def _index_file(self, project_id: str, rel_path: str) -> None:
        """Read, chunk, extract symbols, and persist single file records."""
        full_path = self.workspace_root / rel_path
        if not full_path.exists() or not full_path.is_file():
            return

        try:
            stat = full_path.stat()
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        file_id = uuid.uuid4().hex[:12]
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        line_count = len(content.splitlines())
        now_iso = datetime.now(timezone.utc).isoformat()
        lang = self._detect_language(full_path.suffix.lower())

        # 1. Insert indexed_files record
        self.store.execute_write(
            """
            INSERT OR REPLACE INTO indexed_files
            (id, project_id, file_path, file_hash, line_count, file_size_bytes, modified_at, language, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                file_id,
                project_id,
                rel_path,
                file_hash,
                line_count,
                stat.st_size,
                stat.st_mtime,
                lang,
                now_iso,
            ),
        )

        # 2. Extract and insert symbols
        symbols = self.symbol_extractor.extract_symbols(rel_path, content)
        for sym in symbols:
            sym_id = uuid.uuid4().hex[:12]
            self.store.execute_write(
                """
                INSERT INTO code_symbols
                (id, project_id, file_id, file_path, name, symbol_type, line_start, line_end, signature, docstring, parent_symbol)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    sym_id,
                    project_id,
                    file_id,
                    rel_path,
                    sym.name,
                    sym.symbol_type,
                    sym.line_start,
                    sym.line_end,
                    sym.signature,
                    sym.docstring,
                    sym.parent_symbol,
                ),
            )

        # 3. Chunk and insert code chunks
        chunks = self.chunker.chunk_file(rel_path, content, symbols=symbols)
        for chunk in chunks:
            chunk_id = uuid.uuid4().hex[:12]
            self.store.execute_write(
                """
                INSERT INTO code_chunks
                (id, project_id, file_id, file_path, chunk_index, line_start, line_end, content, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    chunk_id,
                    project_id,
                    file_id,
                    rel_path,
                    chunk.chunk_index,
                    chunk.line_start,
                    chunk.line_end,
                    chunk.content,
                    chunk.content_hash,
                ),
            )

        # 4. Extract and insert import relationships
        imports = self.import_analyzer.extract_imports(rel_path, content)
        for imp in imports:
            imp_id = uuid.uuid4().hex[:12]
            syms_str = ",".join(imp.imported_symbols) if imp.imported_symbols else None
            self.store.execute_write(
                """
                INSERT INTO import_relationships
                (id, project_id, source_file, imported_module, imported_symbols, line_number)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    imp_id,
                    project_id,
                    rel_path,
                    imp.imported_module,
                    syms_str,
                    imp.line_number,
                ),
            )

    def _remove_file_from_index(self, project_id: str, rel_path: str) -> None:
        """Remove file and cascade delete symbols, chunks, and imports."""
        row = self.store.execute_query_one(
            "SELECT id FROM indexed_files WHERE project_id = ? AND file_path = ?;",
            (project_id, rel_path),
        )
        if row:
            file_id = row["id"]
            self.store.execute_write("DELETE FROM code_symbols WHERE file_id = ?;", (file_id,))
            self.store.execute_write("DELETE FROM code_chunks WHERE file_id = ?;", (file_id,))
            self.store.execute_write("DELETE FROM import_relationships WHERE project_id = ? AND source_file = ?;", (project_id, rel_path))
            self.store.execute_write("DELETE FROM indexed_files WHERE id = ?;", (file_id,))

    def _clear_project_index(self, project_id: str) -> None:
        """Clear all indexed data for a project."""
        self.store.execute_write("DELETE FROM code_symbols WHERE project_id = ?;", (project_id,))
        self.store.execute_write("DELETE FROM code_chunks WHERE project_id = ?;", (project_id,))
        self.store.execute_write("DELETE FROM import_relationships WHERE project_id = ?;", (project_id,))
        self.store.execute_write("DELETE FROM indexed_files WHERE project_id = ?;", (project_id,))

    def _has_any_index(self, project_id: str) -> bool:
        """Check if project has any records in indexed_files."""
        row = self.store.execute_query_one(
            "SELECT COUNT(*) as cnt FROM indexed_files WHERE project_id = ?;",
            (project_id,),
        )
        return bool(row and row["cnt"] > 0)

    def _detect_language(self, ext: str) -> str:
        """Map file extension to primary programming language."""
        mapping = {
            ".py": "Python",
            ".js": "JavaScript",
            ".jsx": "React JSX",
            ".ts": "TypeScript",
            ".tsx": "React TSX",
            ".java": "Java",
            ".c": "C",
            ".cpp": "C++",
            ".cc": "C++",
            ".h": "C/C++ Header",
            ".hpp": "C++ Header",
            ".html": "HTML",
            ".css": "CSS",
            ".json": "JSON",
            ".toml": "TOML",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".md": "Markdown",
            ".sql": "SQL",
            ".sh": "Shell",
            ".bat": "Batch",
            ".ps1": "PowerShell",
        }
        return mapping.get(ext, "Unknown")
