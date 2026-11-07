"""Memory cleanup and maintenance utility managing deduplication, stale records, and secret purging."""

import sqlite3
from typing import Any, Dict, List

from codeagent.conversation.storage import scrub_secrets
from codeagent.memory.memory_store import MemoryStore


class MemoryCleanup:
    """Performs database maintenance, deduplication, and credential scrubbing across memory stores."""

    def __init__(self, store: MemoryStore) -> None:
        """Initialize MemoryCleanup with MemoryStore."""
        self.store = store

    def deduplicate(self, project_id: str) -> int:
        """Find duplicate memories with identical (project_id, category, key) and keep the newest.

        Returns:
            int: Number of duplicate records removed.
        """
        rows = self.store.execute_query(
            """
            SELECT category, key, COUNT(*) as cnt
            FROM project_memories
            WHERE project_id = ?
            GROUP BY category, key
            HAVING cnt > 1;
            """,
            (project_id,),
        )

        removed_count = 0
        for r in rows:
            cat = r["category"]
            k = r["key"]
            # Get all IDs ordered by updated_at desc
            item_rows = self.store.execute_query(
                """
                SELECT id FROM project_memories
                WHERE project_id = ? AND category = ? AND key = ?
                ORDER BY updated_at DESC;
                """,
                (project_id, cat, k),
            )
            # Keep first (newest), delete remainder
            to_delete = [row["id"] for row in item_rows[1:]]
            for mem_id in to_delete:
                self.store.execute_write("DELETE FROM project_memories WHERE id = ?;", (mem_id,))
                removed_count += 1

        return removed_count

    def purge_secrets(self) -> int:
        """Scan all stored memories and scrub any credential patterns found in keys or values.

        Returns:
            int: Number of memory rows cleaned.
        """
        rows = self.store.execute_query("SELECT id, key, value FROM project_memories;")
        cleaned_count = 0

        for r in rows:
            orig_k = r["key"]
            orig_v = r["value"]
            clean_k = scrub_secrets(orig_k)
            clean_v = scrub_secrets(orig_v)

            if orig_k != clean_k or orig_v != clean_v:
                self.store.execute_write(
                    "UPDATE project_memories SET key = ?, value = ? WHERE id = ?;",
                    (clean_k, clean_v, r["id"]),
                )
                cleaned_count += 1

        return cleaned_count

    def delete_by_id(self, memory_id: str) -> bool:
        """Delete a memory record by ID."""
        count = self.store.execute_write("DELETE FROM project_memories WHERE id = ?;", (memory_id,))
        return count > 0

    def delete_by_key(self, project_id: str, key: str) -> int:
        """Delete memories matching a specific key within a project."""
        return self.store.execute_write(
            "DELETE FROM project_memories WHERE project_id = ? AND key = ?;",
            (project_id, key.strip()),
        )

    def vacuum_database(self) -> None:
        """Run VACUUM and optimize database storage."""
        with self.store.get_connection() as conn:
            conn.execute("VACUUM;")


MemoryCleanupManager = MemoryCleanup
