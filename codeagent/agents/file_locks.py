"""File lock manager preventing race conditions and concurrent writes in multi-agent workflows."""

from pathlib import Path
import threading
import time
from typing import Dict, Optional, Set


class FileLockError(Exception):
    """Raised when file acquisition fails due to contention or timeout."""
    pass


class FileLockManager:
    """Coordinates file-level locking across concurrent agents to prevent write conflicts."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        """Initialize FileLockManager."""
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self._mutex = threading.Lock()
        # Maps canonical file path -> agent_id owning lock
        self._locks: Dict[str, str] = {}
        # Maps canonical file path -> timestamp of acquisition
        self._lock_times: Dict[str, float] = {}

    def _canonicalize(self, file_path: str) -> str:
        """Normalize file path to absolute canonical string."""
        p = Path(file_path)
        if not p.is_absolute():
            p = (self.workspace_root / p).resolve()
        else:
            p = p.resolve()
        return str(p)

    def acquire(self, file_path: str, agent_id: str, timeout: float = 10.0) -> bool:
        """Attempt to acquire exclusive write lock for a target file path.

        Args:
            file_path: Relative or absolute path to file.
            agent_id: Unique ID of agent requesting the lock.
            timeout: Maximum seconds to wait before failing.

        Returns:
            bool: True if lock was acquired, False if timed out.
        """
        canon = self._canonicalize(file_path)
        start_time = time.time()

        while True:
            with self._mutex:
                current_owner = self._locks.get(canon)
                if current_owner is None or current_owner == agent_id:
                    self._locks[canon] = agent_id
                    self._lock_times[canon] = time.time()
                    return True

            if (time.time() - start_time) >= timeout:
                return False

            time.sleep(0.05)

    def release(self, file_path: str, agent_id: str) -> bool:
        """Release exclusive lock on target file.

        Args:
            file_path: Relative or absolute path to file.
            agent_id: Unique ID of agent releasing the lock.

        Returns:
            bool: True if released, False if not owned by this agent.
        """
        canon = self._canonicalize(file_path)
        with self._mutex:
            current_owner = self._locks.get(canon)
            if current_owner == agent_id:
                del self._locks[canon]
                self._lock_times.pop(canon, None)
                return True
            return False

    def is_locked(self, file_path: str) -> bool:
        """Check if file is currently locked."""
        canon = self._canonicalize(file_path)
        with self._mutex:
            return canon in self._locks

    def get_owner(self, file_path: str) -> Optional[str]:
        """Return agent_id of lock owner, or None if unlocked."""
        canon = self._canonicalize(file_path)
        with self._mutex:
            return self._locks.get(canon)

    def release_all(self, agent_id: str) -> None:
        """Release all locks held by a specific agent (e.g. on exit or failure)."""
        with self._mutex:
            to_remove = [p for p, owner in self._locks.items() if owner == agent_id]
            for p in to_remove:
                del self._locks[p]
                self._lock_times.pop(p, None)

    def clear(self) -> None:
        """Clear all locks forcefully."""
        with self._mutex:
            self._locks.clear()
            self._lock_times.clear()

