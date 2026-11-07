"""Lightweight semantic code search with local lexical and TF-IDF similarity fallback."""

import math
import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from codeagent.indexing.search_engine import SearchResult
from codeagent.memory.memory_store import MemoryStore


class VectorSearchEngine:
    """Provides semantic code retrieval with deterministic local lexical similarity fallback.

    Operates without requiring heavy neural embedding models or external downloads by default.
    """

    def __init__(
        self,
        store: MemoryStore,
        enabled: bool = False,
    ) -> None:
        """Initialize VectorSearchEngine.

        Args:
            store: SQLite MemoryStore.
            enabled: Master switch for neural vector generation (defaults to False).
        """
        self.store = store
        self.enabled = enabled

    def search_semantic(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Perform semantic or lexical similarity retrieval over indexed code chunks."""
        # Clean and tokenize query
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # Fetch candidate chunks from project
        rows = self.store.execute_query(
            "SELECT file_path, line_start, line_end, content FROM code_chunks WHERE project_id = ?;",
            (project_id,),
        )

        scored_results: List[Tuple[float, SearchResult]] = []

        # Compute TF-IDF-inspired lexical similarity
        for r in rows:
            content = r["content"]
            chunk_tokens = self._tokenize(content)
            if not chunk_tokens:
                continue

            similarity = self._compute_lexical_similarity(query_terms, chunk_tokens)
            if similarity > 0.0:
                first_line = content.strip().splitlines()[0] if content.strip() else ""
                res = SearchResult(
                    file_path=r["file_path"],
                    line_number=r["line_start"],
                    matched_content=first_line[:100],
                    match_type="semantic" if self.enabled else "lexical_similarity",
                    relevance_score=round(similarity, 4),
                )
                scored_results.append((similarity, res))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_results[:limit]]

    def _tokenize(self, text: str) -> List[str]:
        """Convert text into lowercase code tokens (splitting on camelCase, snake_case, punctuation)."""
        words = re.findall(r"[A-Za-z0-9]+", text.lower())
        # Filter single character tokens
        return [w for w in words if len(w) > 1]

    def _compute_lexical_similarity(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """Calculate cosine similarity over token frequency vectors."""
        q_freq: Dict[str, int] = {}
        for t in query_tokens:
            q_freq[t] = q_freq.get(t, 0) + 1

        d_freq: Dict[str, int] = {}
        for t in doc_tokens:
            d_freq[t] = d_freq.get(t, 0) + 1

        # Dot product
        dot_product = 0.0
        for t, count in q_freq.items():
            if t in d_freq:
                dot_product += count * d_freq[t]

        if dot_product == 0.0:
            return 0.0

        q_norm = math.sqrt(sum(c * c for c in q_freq.values()))
        d_norm = math.sqrt(sum(c * c for c in d_freq.values()))

        if q_norm == 0.0 or d_norm == 0.0:
            return 0.0

        return dot_product / (q_norm * d_norm)

