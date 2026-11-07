"""Multi-strategy code search engine querying indexed files, symbols, and content chunks."""

import fnmatch
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from codeagent.memory.memory_store import MemoryStore


class SearchResult(BaseModel):
    """Structured code search match."""

    file_path: str
    line_number: int
    matched_content: str
    match_type: str  # "filename", "exact_text", "regex", "function", "class", "symbol", "chunk"
    relevance_score: float = 1.0

    def to_summary(self) -> str:
        """Format an informative one-line summary."""
        preview = self.matched_content.strip()[:80]
        return f"{self.file_path}:{self.line_number} [{self.match_type.upper()}] {preview}"


class SearchEngine:
    """Queries indexed source code symbols, file paths, and chunk content."""

    def __init__(self, store: MemoryStore) -> None:
        """Initialize SearchEngine with SQLite MemoryStore."""
        self.store = store

    def search_filename(self, project_id: str, pattern: str, limit: int = 20) -> List[SearchResult]:
        """Search project file paths matching a glob or substring pattern."""
        rows = self.store.execute_query(
            "SELECT file_path FROM indexed_files WHERE project_id = ?;",
            (project_id,),
        )
        results: List[SearchResult] = []
        clean_pat = pattern.strip().lower()

        for r in rows:
            fpath = r["file_path"]
            fpath_low = fpath.lower()
            fname = Path(fpath).name.lower()

            if fnmatch.fnmatch(fname, clean_pat) or clean_pat in fpath_low:
                score = 2.0 if clean_pat == fname else 1.0
                results.append(
                    SearchResult(
                        file_path=fpath,
                        line_number=1,
                        matched_content=fpath,
                        match_type="filename",
                        relevance_score=score,
                    )
                )

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]

    def search_symbol(
        self,
        project_id: str,
        name: str,
        symbol_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[SearchResult]:
        """Search code symbols (functions, classes, methods) by name."""
        pattern = f"%{name.strip()}%"
        if symbol_type:
            rows = self.store.execute_query(
                """
                SELECT file_path, line_start, name, symbol_type, signature, docstring
                FROM code_symbols
                WHERE project_id = ? AND symbol_type = ? AND name LIKE ?
                ORDER BY CASE WHEN name = ? THEN 1 ELSE 2 END, line_start ASC
                LIMIT ?;
                """,
                (project_id, symbol_type, pattern, name.strip(), limit),
            )
        else:
            rows = self.store.execute_query(
                """
                SELECT file_path, line_start, name, symbol_type, signature, docstring
                FROM code_symbols
                WHERE project_id = ? AND name LIKE ?
                ORDER BY CASE WHEN name = ? THEN 1 ELSE 2 END, line_start ASC
                LIMIT ?;
                """,
                (project_id, pattern, name.strip(), limit),
            )

        results: List[SearchResult] = []
        for r in rows:
            is_exact = r["name"] == name.strip()
            score = 3.0 if is_exact else 1.5
            sig = r["signature"] or r["name"]
            results.append(
                SearchResult(
                    file_path=r["file_path"],
                    line_number=r["line_start"],
                    matched_content=sig,
                    match_type=r["symbol_type"] if r["symbol_type"] in ("function", "class") else "symbol",
                    relevance_score=score,
                )
            )
        return results

    def search_function(self, project_id: str, name: str, limit: int = 20) -> List[SearchResult]:
        """Convenience method for searching functions and methods."""
        return self.search_symbol(project_id=project_id, name=name, symbol_type="function", limit=limit)

    def search_class(self, project_id: str, name: str, limit: int = 20) -> List[SearchResult]:
        """Convenience method for searching classes and structs."""
        return self.search_symbol(project_id=project_id, name=name, symbol_type="class", limit=limit)

    def search_exact_text(self, project_id: str, query: str, limit: int = 20) -> List[SearchResult]:
        """Search code chunks containing exact substring query."""
        pattern = f"%{query.strip()}%"
        rows = self.store.execute_query(
            """
            SELECT file_path, line_start, line_end, content
            FROM code_chunks
            WHERE project_id = ? AND content LIKE ?
            LIMIT ?;
            """,
            (project_id, pattern, limit * 2),
        )

        results: List[SearchResult] = []
        q_strip = query.strip()
        for r in rows:
            content = r["content"]
            lines = content.splitlines()
            start_l = r["line_start"]

            # Locate matching line
            for offset, line in enumerate(lines):
                if q_strip in line:
                    results.append(
                        SearchResult(
                            file_path=r["file_path"],
                            line_number=start_l + offset,
                            matched_content=line.strip(),
                            match_type="exact_text",
                            relevance_score=1.5,
                        )
                    )
                    break

        return results[:limit]

    def search_regex(self, project_id: str, regex_pattern: str, limit: int = 20) -> List[SearchResult]:
        """Search code chunks matching regular expression."""
        try:
            compiled = re.compile(regex_pattern)
        except re.error as err:
            raise ValueError(f"Invalid regular expression '{regex_pattern}': {err}")

        # Fetch candidate chunks
        rows = self.store.execute_query(
            "SELECT file_path, line_start, content FROM code_chunks WHERE project_id = ?;",
            (project_id,),
        )

        results: List[SearchResult] = []
        for r in rows:
            content = r["content"]
            lines = content.splitlines()
            start_l = r["line_start"]

            for offset, line in enumerate(lines):
                if compiled.search(line):
                    results.append(
                        SearchResult(
                            file_path=r["file_path"],
                            line_number=start_l + offset,
                            matched_content=line.strip(),
                            match_type="regex",
                            relevance_score=1.2,
                        )
                    )
                    if len(results) >= limit:
                        return results

        return results

    def search_content_chunks(self, project_id: str, query: str, limit: int = 10) -> List[SearchResult]:
        """Search code chunks using keyword matching."""
        terms = [t.strip() for t in query.split() if len(t.strip()) > 2]
        if not terms:
            return self.search_exact_text(project_id=project_id, query=query, limit=limit)

        results: List[SearchResult] = []
        # Search for primary term
        primary_pattern = f"%{terms[0]}%"
        rows = self.store.execute_query(
            """
            SELECT file_path, line_start, line_end, content
            FROM code_chunks
            WHERE project_id = ? AND content LIKE ?
            LIMIT ?;
            """,
            (project_id, primary_pattern, limit * 3),
        )

        for r in rows:
            content = r["content"]
            matches = sum(1 for term in terms if term.lower() in content.lower())
            if matches > 0:
                first_line = content.strip().splitlines()[0] if content.strip() else ""
                results.append(
                    SearchResult(
                        file_path=r["file_path"],
                        line_number=r["line_start"],
                        matched_content=first_line,
                        match_type="chunk",
                        relevance_score=float(matches),
                    )
                )

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]

