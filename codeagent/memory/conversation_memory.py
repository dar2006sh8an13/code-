"""Conversation memory indexing session metadata and summarizing dialog history in SQLite."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from codeagent.conversation.storage import ConversationStorage, scrub_secrets
from codeagent.llm.client import LLMClient
from codeagent.memory.memory_store import MemoryStore


class ConversationSummary(BaseModel):
    """Structured representation of a summarized conversation."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    project_id: str
    conversation_id: str
    summary: str
    message_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ConversationMemory:
    """Manages persistent conversation records, titles, and summaries tied to projects."""

    def __init__(
        self,
        store: MemoryStore,
        storage: Optional[ConversationStorage] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        """Initialize ConversationMemory.

        Args:
            store: MemoryStore SQLite instance.
            storage: Optional ConversationStorage instance for raw JSON loading.
            llm_client: Optional LLMClient for AI summarization.
        """
        self.store = store
        self.storage = storage or ConversationStorage()
        self.llm_client = llm_client

    def register_conversation(
        self,
        project_id: str,
        conversation_id: str,
        title: Optional[str] = None,
    ) -> None:
        """Register or update a conversation in SQLite."""
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_title = scrub_secrets(title or f"Conversation {conversation_id}")

        existing = self.store.execute_query_one(
            "SELECT id FROM conversations WHERE id = ?;",
            (conversation_id,),
        )
        if existing:
            self.store.execute_write(
                "UPDATE conversations SET project_id = ?, title = ?, updated_at = ? WHERE id = ?;",
                (project_id, clean_title, now_iso, conversation_id),
            )
        else:
            self.store.execute_write(
                """
                INSERT INTO conversations (id, project_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (conversation_id, project_id, clean_title, now_iso, now_iso),
            )

    def list_conversations(self, project_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """List registered conversations for a project."""
        rows = self.store.execute_query(
            "SELECT * FROM conversations WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?;",
            (project_id, limit),
        )
        return [dict(r) for r in rows]

    def record_summary(
        self,
        project_id: str,
        conversation_id: str,
        summary_text: Optional[str] = None,
        message_count: int = 0,
        summary: Optional[str] = None,
    ) -> ConversationSummary:
        """Persist a conversation summary in SQLite."""
        # Ensure conversation exists to satisfy foreign key constraint
        self.register_conversation(project_id=project_id, conversation_id=conversation_id)

        raw_text = summary_text if summary_text is not None else (summary or "")
        clean_summary = scrub_secrets(raw_text.strip())
        summary_id = uuid.uuid4().hex[:12]
        now_iso = datetime.now(timezone.utc).isoformat()

        self.store.execute_write(
            """
            INSERT INTO conversation_summaries (id, project_id, conversation_id, summary, message_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (summary_id, project_id, conversation_id, clean_summary, message_count, now_iso),
        )

        return ConversationSummary(
            id=summary_id,
            project_id=project_id,
            conversation_id=conversation_id,
            summary=clean_summary,
            message_count=message_count,
            created_at=now_iso,
        )

    save_summary = record_summary

    def get_latest_summaries(self, project_id: str, limit: int = 5) -> List[ConversationSummary]:
        """Retrieve recent conversation summaries for a project."""
        rows = self.store.execute_query(
            """
            SELECT * FROM conversation_summaries
            WHERE project_id = ?
            ORDER BY created_at DESC LIMIT ?;
            """,
            (project_id, limit),
        )
        return [ConversationSummary(**dict(r)) for r in rows]

    list_summaries = get_latest_summaries

    def summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Create a compact summary of conversation messages using LLM or rule-based fallback."""
        if not messages:
            return "Empty conversation."

        # Filter out tool output blobs to keep summary concise
        dialog_lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))
            if role in ("user", "assistant") and content.strip():
                snippet = content.strip().split("\n")[0][:120]
                dialog_lines.append(f"{role.capitalize()}: {snippet}")

        raw_dialog = "\n".join(dialog_lines[-10:])

        if self.llm_client:
            prompt = (
                "Summarize the main topics, user intents, and outcomes of this conversation "
                "in 2-3 concise sentences. Focus on project decisions and technical tasks:\n\n"
                f"{raw_dialog}"
            )
            try:
                res = self.llm_client.generate(prompt=prompt, system_prompt="You are a concise conversation summarizer.")
                if res and res.strip():
                    return scrub_secrets(res.strip())
            except Exception:
                pass

        # Extractive deterministic fallback
        topics = [line for line in dialog_lines if line.startswith("User:")][:3]
        return "Discussion regarding: " + "; ".join(topics) if topics else "Development and coding discussion."


ConversationMemoryManager = ConversationMemory
