"""Project memory domain storing and querying facts, conventions, and architectural decisions."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
import uuid
from pydantic import BaseModel, Field

from codeagent.conversation.storage import scrub_secrets
from codeagent.memory.memory_store import MemoryStore


class MemoryCategory(str, Enum):
    """Classification for stored project knowledge."""

    ARCHITECTURE = "architecture"
    CONVENTION = "convention"
    DECISION = "decision"
    LIMITATION = "limitation"
    DEPENDENCY = "dependency"
    STACK = "stack"
    GENERAL = "general"


class ProjectFact(BaseModel):
    """Structured representation of a single persisted project fact."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    project_id: str
    category: str = MemoryCategory.GENERAL.value
    key: str
    value: str
    source: str = "user"
    confidence: float = 1.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_summary(self) -> str:
        """Format an informative summary of this memory."""
        return f"[{self.category.upper()}] {self.key}: {self.value}"


class ProjectMemory:
    """Manages project-scoped facts, decisions, and constraints in SQLite."""

    def __init__(self, store: MemoryStore) -> None:
        """Initialize ProjectMemory with underlying SQLite store."""
        self.store = store

    def store_fact(
        self,
        project_id: str,
        key: str,
        value: str,
        category: str = MemoryCategory.GENERAL.value,
        source: str = "user",
        confidence: float = 1.0,
    ) -> ProjectFact:
        """Store or update a project-specific fact with secret scrubbing."""
        categories = {c.value for c in MemoryCategory}
        if key in categories and (category not in categories or category == MemoryCategory.GENERAL.value):
            # Positional pattern: (project_id, category, key, value, confidence)
            real_cat = key
            real_key = value
            real_val = category
            real_conf = confidence
            if isinstance(source, (int, float)):
                real_conf = float(source)
                source = "user"
            category, key, value, confidence = real_cat, real_key, real_val, real_conf

        # Sanitize sensitive patterns
        clean_key = scrub_secrets(key.strip())
        clean_val = scrub_secrets(value.strip())
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check if key already exists in project and category
        row = self.store.execute_query_one(
            "SELECT id, created_at FROM project_memories WHERE project_id = ? AND category = ? AND key = ?;",
            (project_id, category, clean_key),
        )

        if row:
            fact_id = row["id"]
            created_at = row["created_at"]
            self.store.execute_write(
                """
                UPDATE project_memories
                SET value = ?, source = ?, confidence = ?, updated_at = ?
                WHERE id = ?;
                """,
                (clean_val, source, confidence, now_iso, fact_id),
            )
            return ProjectFact(
                id=fact_id,
                project_id=project_id,
                category=category,
                key=clean_key,
                value=clean_val,
                source=source,
                confidence=confidence,
                created_at=created_at,
                updated_at=now_iso,
            )

        fact = ProjectFact(
            project_id=project_id,
            category=category,
            key=clean_key,
            value=clean_val,
            source=source,
            confidence=confidence,
            created_at=now_iso,
            updated_at=now_iso,
        )

        self.store.execute_write(
            """
            INSERT INTO project_memories (id, project_id, category, key, value, source, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                fact.id,
                fact.project_id,
                fact.category,
                fact.key,
                fact.value,
                fact.source,
                fact.confidence,
                fact.created_at,
                fact.updated_at,
            ),
        )
        return fact

    def get_fact(
        self,
        fact_id: Optional[str] = None,
        project_id: Optional[str] = None,
        key: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[ProjectFact]:
        """Retrieve a specific memory fact by ID, or by project_id and key."""
        if fact_id:
            row = self.store.execute_query_one(
                "SELECT * FROM project_memories WHERE id = ?;",
                (fact_id,),
            )
        elif project_id and key:
            if category:
                row = self.store.execute_query_one(
                    "SELECT * FROM project_memories WHERE project_id = ? AND category = ? AND key = ?;",
                    (project_id, category, key),
                )
            else:
                row = self.store.execute_query_one(
                    "SELECT * FROM project_memories WHERE project_id = ? AND key = ?;",
                    (project_id, key),
                )
        else:
            return None

        if not row:
            return None
        return ProjectFact(**dict(row))

    def list_facts(
        self,
        project_id: str,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[ProjectFact]:
        """List stored facts for a project, optionally filtered by category."""
        if category:
            rows = self.store.execute_query(
                "SELECT * FROM project_memories WHERE project_id = ? AND category = ? ORDER BY updated_at DESC LIMIT ?;",
                (project_id, category, limit),
            )
        else:
            rows = self.store.execute_query(
                "SELECT * FROM project_memories WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?;",
                (project_id, limit),
            )
        return [ProjectFact(**dict(r)) for r in rows]

    def search_facts(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> List[ProjectFact]:
        """Search facts for a project by key or value substring."""
        pattern = f"%{query.strip()}%"
        rows = self.store.execute_query(
            """
            SELECT * FROM project_memories
            WHERE project_id = ? AND (key LIKE ? OR value LIKE ? OR category LIKE ?)
            ORDER BY updated_at DESC LIMIT ?;
            """,
            (project_id, pattern, pattern, pattern, limit),
        )
        return [ProjectFact(**dict(r)) for r in rows]

    def delete_fact(self, fact_id: str) -> bool:
        """Delete a single fact by ID."""
        count = self.store.execute_write("DELETE FROM project_memories WHERE id = ?;", (fact_id,))
        return count > 0

    def delete_project_facts(self, project_id: str) -> int:
        """Delete all facts associated with a project."""
        return self.store.execute_write("DELETE FROM project_memories WHERE project_id = ?;", (project_id,))


ProjectMemoryManager = ProjectMemory
