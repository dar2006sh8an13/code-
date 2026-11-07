"""Local JSON storage for conversation histories with security and corruption handling."""

import json
import re
from pathlib import Path
from typing import Any, Optional


class StorageError(Exception):
    """Base exception for conversation storage operations."""
    pass


class ConversationNotFoundError(StorageError):
    """Raised when a requested conversation file does not exist."""
    pass


class CorruptedConversationError(StorageError):
    """Raised when a conversation file cannot be decoded or is invalid."""
    pass


# Regular expressions for scrubbing common secrets, tokens, and credentials
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_\-\s]?key|secret|token|password|auth|credential)\s*[:=]\s*['\"]?([A-Za-z0-9_\-.~+/=]{8,})['\"]?"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.~+/=]{16,}", re.IGNORECASE),
    re.compile(r"(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
]


def scrub_secrets(text: str) -> str:
    """Mask credentials, tokens, and passwords in text before persisting to disk."""
    if not text:
        return text

    scrubbed = text
    for pattern in SECRET_PATTERNS:
        scrubbed = pattern.sub(r"\1=[REDACTED_SECRET]", scrubbed) if "(" in pattern.pattern else pattern.sub("[REDACTED_SECRET]", scrubbed)
    return scrubbed


def sanitize_filename(name: str) -> str:
    """Sanitize a conversation name into a safe filesystem-friendly filename."""
    # Remove directory traversal characters and unsafe characters
    clean = re.sub(r"[^\w\-.]", "_", name.strip())
    clean = re.sub(r"_+", "_", clean).strip("._")
    return clean or "conversation"


class ConversationStorage:
    """Manages reading and writing conversation history files in local JSON format."""

    def __init__(self, base_dir: str | Path = "data/conversations") -> None:
        """Initialize the storage manager with a base directory."""
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_safe_path(self, identifier: str) -> Path:
        """Resolve an identifier to a safe path strictly inside base_dir."""
        if ".." in identifier or "/" in identifier or "\\" in identifier:
            raise StorageError(f"Security violation: path traversal detected in '{identifier}'.")

        safe_name = sanitize_filename(identifier)
        if not safe_name.endswith(".json"):
            safe_name += ".json"

        target_path = (self.base_dir / safe_name).resolve()
        if not str(target_path).startswith(str(self.base_dir)):
            raise StorageError(f"Security violation: path traversal detected in '{identifier}'.")
        return target_path

    def save(self, conversation_data: dict[str, Any], identifier: Optional[str] = None) -> Path:
        """Save conversation dictionary to a local JSON file with secret scrubbing.

        Args:
            conversation_data: Conversation dictionary to serialize.
            identifier: Optional filename/identifier (defaults to conversation_data['id']).

        Returns:
            Path: Absolute path to the saved JSON file.
        """
        conv_id = identifier or str(conversation_data.get("id") or "conversation")
        target_path = self._get_safe_path(conv_id)

        # Recursively scrub secrets in string fields
        clean_data = self._scrub_data(conversation_data)

        temp_path = target_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(clean_data, f, indent=2, ensure_ascii=False)
            # Atomic rename
            temp_path.replace(target_path)
            return target_path
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink()
            raise StorageError(f"Failed to save conversation '{conv_id}': {exc}") from exc

    def load(self, identifier: str) -> dict[str, Any]:
        """Load conversation data from a local JSON file.

        Args:
            identifier: Conversation ID or saved filename.

        Returns:
            dict: The loaded conversation structure.

        Raises:
            ConversationNotFoundError: If file does not exist.
            CorruptedConversationError: If file is malformed JSON or unreadable.
        """
        target_path = self._get_safe_path(identifier)

        if not target_path.exists() or not target_path.is_file():
            raise ConversationNotFoundError(f"Conversation '{identifier}' was not found at {target_path}.")

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise CorruptedConversationError(f"Corrupted format in '{target_path}': expected JSON object.")
            return data
        except json.JSONDecodeError as exc:
            raise CorruptedConversationError(
                f"Conversation file '{target_path.name}' is corrupted: invalid JSON ({exc})."
            ) from exc
        except Exception as exc:
            if isinstance(exc, (ConversationNotFoundError, CorruptedConversationError)):
                raise
            raise StorageError(f"Failed to load conversation '{identifier}': {exc}") from exc

    def list_saved(self) -> list[dict[str, Any]]:
        """List all valid saved conversations in the storage directory.

        Corrupted files are safely skipped without breaking the listing.

        Returns:
            list[dict]: Metadata for each readable conversation file.
        """
        results: list[dict[str, Any]] = []

        for file_path in sorted(self.base_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    results.append({
                        "file_name": file_path.name,
                        "id": data.get("id", file_path.stem),
                        "title": data.get("title", file_path.stem),
                        "message_count": len(data.get("messages", [])),
                        "updated_at": data.get("updated_at", str(file_path.stat().st_mtime)),
                    })
            except Exception:
                # Gracefully skip corrupt or inaccessible files
                continue

        return results

    def _scrub_data(self, data: Any) -> Any:
        """Recursively scrub secrets from strings in nested structures."""
        if isinstance(data, str):
            return scrub_secrets(data)
        elif isinstance(data, dict):
            return {k: self._scrub_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._scrub_data(item) for item in data]
        return data
