"""Memory retriever ranking project facts and conversation summaries for context injection."""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from codeagent.memory.conversation_memory import ConversationMemory, ConversationSummary
from codeagent.memory.project_memory import ProjectFact, ProjectMemory


class RetrievedMemory(BaseModel):
    """Ranked memory item prepared for context inclusion."""

    memory_type: str  # "fact" or "summary"
    category: str
    content: str
    relevance_score: float
    source: str
    key: Optional[str] = None

    @property
    def value(self) -> str:
        """Alias for content."""
        return self.content


class MemoryRetriever:
    """Retrieves and ranks project-scoped facts and historical summaries."""

    def __init__(
        self,
        project_memory: Optional[ProjectMemory] = None,
        conversation_memory: Optional[ConversationMemory] = None,
        store: Optional[Any] = None,
    ) -> None:
        """Initialize MemoryRetriever."""
        if store:
            self.project_memory = project_memory or ProjectMemory(store=store)
            self.conversation_memory = conversation_memory or ConversationMemory(store=store)
        else:
            self.project_memory = project_memory or (ProjectMemory(store=store) if store else None)
            self.conversation_memory = conversation_memory or (ConversationMemory(store=store) if store else None)

    def retrieve(
        self,
        project_id: str,
        query: Optional[str] = None,
        max_results: int = 10,
        category: Optional[str] = None,
        max_tokens: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[RetrievedMemory]:
        """Retrieve top relevant memories for a project matching an optional query string."""
        effective_limit = limit or max_results
        results: List[RetrievedMemory] = []
        clean_q = (query or "").strip().lower()
        query_words = set(re.findall(r"\w+", clean_q))

        # 1. Retrieve all project facts for this project
        facts = self.project_memory.list_facts(project_id=project_id, category=category, limit=100)
        for fact in facts:
            score = self._score_fact(fact, query_words, clean_q)
            results.append(
                RetrievedMemory(
                    memory_type="fact",
                    category=fact.category,
                    content=f"[{fact.category.upper()}] {fact.key}: {fact.value}",
                    relevance_score=score,
                    source=fact.source,
                    key=fact.key,
                )
            )

        # 2. Retrieve recent conversation summaries for this project
        summaries = self.conversation_memory.get_latest_summaries(project_id=project_id, limit=5)
        for summ in summaries:
            score = self._score_text(summ.summary, query_words, clean_q, base_score=0.5)
            results.append(
                RetrievedMemory(
                    memory_type="summary",
                    category="conversation",
                    content=f"[CONVERSATION SUMMARY] {summ.summary}",
                    relevance_score=score,
                    source="conversation_history",
                    key=summ.conversation_id,
                )
            )

        # Sort by relevance score descending
        results.sort(key=lambda m: m.relevance_score, reverse=True)
        return results[:effective_limit]

    def _score_fact(self, fact: ProjectFact, query_words: set[str], full_query: str) -> float:
        """Calculate relevance score for a project fact."""
        # High base weight for architectural and stack facts
        category_weights = {
            "architecture": 1.2,
            "stack": 1.1,
            "convention": 1.1,
            "limitation": 1.0,
            "decision": 1.0,
            "dependency": 0.9,
            "general": 0.8,
        }
        weight = category_weights.get(fact.category, 0.8)

        if not query_words:
            # When no search query is specified, return baseline category importance
            return weight * fact.confidence

        fact_text = f"{fact.key} {fact.value}".lower()

        # Exact substring match bonus
        if full_query in fact_text:
            return 3.0 * weight * fact.confidence

        # Word overlap count
        fact_words = set(re.findall(r"\w+", fact_text))
        overlap = query_words.intersection(fact_words)
        match_ratio = len(overlap) / max(len(query_words), 1)

        return (match_ratio * 2.0 + 0.1) * weight * fact.confidence

    def _score_text(self, text: str, query_words: set[str], full_query: str, base_score: float = 0.5) -> float:
        """Calculate relevance score for free-form summary text."""
        if not query_words:
            return base_score

        low_text = text.lower()
        if full_query in low_text:
            return 2.0

        words = set(re.findall(r"\w+", low_text))
        overlap = query_words.intersection(words)
        match_ratio = len(overlap) / max(len(query_words), 1)
        return match_ratio * 1.5 + 0.05
