"""Conversation history and multi-turn state management."""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from codeagent.conversation.storage import ConversationStorage


@dataclass
class Message:
    """A single turn in a conversation."""

    role: str  # 'system', 'user', 'assistant', 'tool'
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    name: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary format."""
        d = asdict(self)
        # Drop None values to keep representations clean
        return {k: v for k, v in d.items() if v is not None}

    def to_llm_format(self) -> dict[str, Any]:
        """Format message for Ollama chat API."""
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content or "",
        }
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class Conversation:
    """A full conversation session with history metadata."""

    id: str = field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}")
    title: str = "New Conversation"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert conversation to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conversation":
        """Reconstruct a Conversation instance from dictionary data."""
        messages: list[Message] = []
        for m in data.get("messages", []):
            messages.append(
                Message(
                    role=m.get("role", "user"),
                    content=m.get("content", ""),
                    timestamp=m.get("timestamp", datetime.now().isoformat()),
                    name=m.get("name"),
                    tool_calls=m.get("tool_calls"),
                )
            )
        return cls(
            id=data.get("id", f"conv_{uuid.uuid4().hex[:12]}"),
            title=data.get("title", "Saved Conversation"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            messages=messages,
        )


class ConversationManager:
    """Manages active conversation session, message history, and persistence."""

    def __init__(
        self,
        storage_path: str | Path = "data/conversations",
        system_prompt: Optional[str] = None,
    ) -> None:
        """Initialize the conversation manager.

        Args:
            storage_path: Local directory for conversation storage.
            system_prompt: Optional initial system prompt to anchor conversations.
        """
        self.storage = ConversationStorage(storage_path)
        self.system_prompt = system_prompt
        self.active_conversation = self.new_conversation()

    def new_conversation(self, title: Optional[str] = None) -> Conversation:
        """Start a new clean conversation session."""
        conv = Conversation(title=title or "New Conversation")
        if self.system_prompt and self.system_prompt.strip():
            conv.messages.append(Message(role="system", content=self.system_prompt.strip()))
        self.active_conversation = conv
        return conv

    def add_user_message(self, content: str) -> Message:
        """Add a user message to the active conversation."""
        msg = Message(role="user", content=content)
        self.active_conversation.messages.append(msg)
        self.active_conversation.updated_at = datetime.now().isoformat()
        # Auto-update title if it's the first user message and title is default
        if self.active_conversation.title == "New Conversation" and content.strip():
            self.active_conversation.title = content.strip()[:40]
        return msg

    def add_assistant_message(
        self,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
    ) -> Message:
        """Add an assistant message to the active conversation."""
        msg = Message(role="assistant", content=content, tool_calls=tool_calls)
        self.active_conversation.messages.append(msg)
        self.active_conversation.updated_at = datetime.now().isoformat()
        return msg

    def add_tool_message(self, content: str, tool_name: str) -> Message:
        """Add a tool response message to the active conversation."""
        msg = Message(role="tool", content=content, name=tool_name)
        self.active_conversation.messages.append(msg)
        self.active_conversation.updated_at = datetime.now().isoformat()
        return msg

    def add_system_message(self, content: str) -> Message:
        """Add or update a system instruction message."""
        msg = Message(role="system", content=content)
        self.active_conversation.messages.append(msg)
        self.active_conversation.updated_at = datetime.now().isoformat()
        return msg

    def clear(self) -> None:
        """Clear all messages in the active conversation while keeping its ID."""
        self.active_conversation.messages.clear()
        if self.system_prompt and self.system_prompt.strip():
            self.active_conversation.messages.append(
                Message(role="system", content=self.system_prompt.strip())
            )
        self.active_conversation.updated_at = datetime.now().isoformat()

    def get_messages_for_llm(self) -> list[dict[str, Any]]:
        """Return the conversation messages formatted for the Ollama chat API."""
        return [m.to_llm_format() for m in self.active_conversation.messages]

    def save(self, identifier: Optional[str] = None) -> Path:
        """Persist the active conversation to disk."""
        target_id = identifier or self.active_conversation.id
        return self.storage.save(self.active_conversation.to_dict(), identifier=target_id)

    def load(self, identifier: str) -> Conversation:
        """Load a conversation from disk and set it as active."""
        data = self.storage.load(identifier)
        self.active_conversation = Conversation.from_dict(data)
        return self.active_conversation

    def list_saved(self) -> list[dict[str, Any]]:
        """List metadata for all saved conversations."""
        return self.storage.list_saved()

