"""SQLite relational storage engine with versioned schema and multi-project isolation."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union


CURRENT_SCHEMA_VERSION = 1


class MemoryStore:
    """Manages persistent SQLite storage for projects, symbols, chunks, and memories."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        """Initialize MemoryStore with database file path.

        Args:
            db_path: Path to the SQLite database file. Defaults to data/projects/codeagent.db.
        """
        if db_path is None:
            base_dir = Path("data/projects").resolve()
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_dir / "codeagent.db"
        else:
            self.db_path = Path(db_path).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create and return a configured SQLite connection."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self) -> None:
        """Initialize database tables and indexes with schema versioning."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Metadata table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

            # Check schema version
            cursor.execute("SELECT value FROM memory_metadata WHERE key = 'schema_version';")
            row = cursor.fetchone()
            if not row:
                self._create_schema(cursor)
                cursor.execute(
                    "INSERT INTO memory_metadata (key, value) VALUES ('schema_version', ?);",
                    (str(CURRENT_SCHEMA_VERSION),),
                )
            conn.commit()

    def _create_schema(self, cursor: sqlite3.Cursor) -> None:
        """Execute DDL statements to create all required tables and indexes."""
        # 1. Projects table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        # 2. Indexed files table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_files (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                line_count INTEGER NOT NULL DEFAULT 0,
                file_size_bytes INTEGER NOT NULL DEFAULT 0,
                modified_at REAL NOT NULL,
                language TEXT,
                indexed_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE (project_id, file_path)
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_proj ON indexed_files(project_id, file_path);")

        # 3. Code symbols table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS code_symbols (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                name TEXT NOT NULL,
                symbol_type TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                signature TEXT,
                docstring TEXT,
                parent_symbol TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES indexed_files(id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_proj ON code_symbols(project_id, name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_type ON code_symbols(project_id, symbol_type);")

        # 4. Code chunks table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS code_chunks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES indexed_files(id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_proj ON code_chunks(project_id, file_path);")

        # 5. Import relationships table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS import_relationships (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_file TEXT NOT NULL,
                imported_module TEXT NOT NULL,
                imported_symbols TEXT,
                line_number INTEGER NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_imports_proj ON import_relationships(project_id, source_file);")

        # 6. Conversations table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_proj ON conversations(project_id);")

        # 7. Conversation summaries table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_sum_proj ON conversation_summaries(project_id);")

        # 8. Project memories table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS project_memories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_proj_cat ON project_memories(project_id, category);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_proj_key ON project_memories(project_id, key);")

    def execute_write(self, query: str, params: Tuple[Any, ...] = ()) -> int:
        """Execute an insert, update, or delete query and return affected row count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount

    def execute_many(self, query: str, params_seq: List[Tuple[Any, ...]]) -> int:
        """Execute batch insert/update query across a sequence of parameters."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_seq)
            conn.commit()
            return cursor.rowcount

    def execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
        """Execute a select query and return all matching rows."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute_query_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
        """Execute a select query and return a single row or None."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
