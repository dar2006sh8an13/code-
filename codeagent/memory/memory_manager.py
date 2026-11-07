"""Central memory manager coordinating facts, conversations, retrieval, and cleanup."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from codeagent.config.settings import Settings, get_settings
from codeagent.llm.client import LLMClient
from codeagent.memory.conversation_memory import ConversationMemory, ConversationSummary
from codeagent.memory.memory_cleanup import MemoryCleanup
from codeagent.memory.memory_retriever import MemoryRetriever, RetrievedMemory
from codeagent.memory.memory_store import MemoryStore
from codeagent.memory.project_memory import MemoryCategory, ProjectFact, ProjectMemory


class MemoryManager:
    """Coordinates project-scoped memory creation, querying, retrieval, and maintenance."""

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        settings: Optional[Settings] = None,
        llm_client: Optional[LLMClient] = None,
        store: Optional[MemoryStore] = None,
    ) -> None:
        """Initialize MemoryManager with settings and database store."""
        self.settings = settings or get_settings()
        self.llm_client = llm_client

        if store is not None:
            self.store = store
            self.db_path = store.db_path
        else:
            if db_path is None:
                data_dir = Path(self.settings.project_data_path).resolve()
                data_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = data_dir / "codeagent.db"
            else:
                self.db_path = Path(db_path).resolve()
            self.store = MemoryStore(db_path=self.db_path)

        self.project_memory = ProjectMemory(store=self.store)
        self.conversation_memory = ConversationMemory(store=self.store, llm_client=self.llm_client)
        self.retriever = MemoryRetriever(
            project_memory=self.project_memory,
            conversation_memory=self.conversation_memory,
        )
        self.cleanup = MemoryCleanup(store=self.store)

    def store_fact(
        self,
        project_id: str,
        key: str,
        value: str,
        category: str = MemoryCategory.GENERAL.value,
        source: str = "user",
        confidence: float = 1.0,
    ) -> ProjectFact:
        """Store or update a project memory fact."""
        categories = {c.value for c in MemoryCategory}
        if key in categories and (category not in categories or category == MemoryCategory.GENERAL.value):
            real_cat = key
            real_key = value
            real_val = category
            real_conf = confidence
            if isinstance(source, (int, float)):
                real_conf = float(source)
                source = "user"
            category, key, value, confidence = real_cat, real_key, real_val, real_conf

        return self.project_memory.store_fact(
            project_id=project_id,
            key=key,
            value=value,
            category=category,
            source=source,
            confidence=confidence,
        )

    def get_fact(self, fact_id: str) -> Optional[ProjectFact]:
        """Retrieve a specific fact by ID."""
        return self.project_memory.get_fact(fact_id)

    def list_facts(
        self,
        project_id: str,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[ProjectFact]:
        """List stored facts for a project."""
        return self.project_memory.list_facts(project_id=project_id, category=category, limit=limit)

    def search_facts(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> List[ProjectFact]:
        """Search facts within a project by substring."""
        return self.project_memory.search_facts(project_id=project_id, query=query, limit=limit)

    def delete_fact(self, fact_id: str) -> bool:
        """Delete a fact by ID."""
        return self.project_memory.delete_fact(fact_id)

    def retrieve_context_memories(
        self,
        project_id: str,
        query: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[RetrievedMemory]:
        """Retrieve ranked memories (facts and conversation summaries) for prompt context."""
        limit = max_results or self.settings.memory_max_results
        return self.retriever.retrieve(project_id=project_id, query=query, max_results=limit)

    def record_conversation_summary(
        self,
        project_id: str,
        conversation_id: str,
        summary_text: Optional[str] = None,
        message_count: int = 0,
        summary: Optional[str] = None,
    ) -> ConversationSummary:
        """Record a conversation summary for historical context."""
        text = summary_text if summary_text is not None else (summary or "")
        return self.conversation_memory.record_summary(
            project_id=project_id,
            conversation_id=conversation_id,
            summary_text=text,
            message_count=message_count,
        )

    def cleanup_duplicates(self, project_id: str) -> int:
        """Remove duplicate memories in a project."""
        return self.cleanup.deduplicate(project_id)

    retrieve_memories = retrieve_context_memories
    save_conversation_summary = record_conversation_summary

    def list_conversation_summaries(self, project_id: str, limit: int = 20) -> List[ConversationSummary]:
        """List conversation summaries for a project."""
        return self.conversation_memory.get_latest_summaries(project_id=project_id, limit=limit)
