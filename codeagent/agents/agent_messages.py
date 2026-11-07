"""Agent messaging, structured communication protocol, and in-process message bus."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Supported agent message types."""

    TASK_ASSIGNMENT = "TASK_ASSIGNMENT"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_BLOCKED = "TASK_BLOCKED"
    REVIEW_REQUEST = "REVIEW_REQUEST"
    REVIEW_RESULT = "REVIEW_RESULT"
    DEBUG_REQUEST = "DEBUG_REQUEST"
    DEBUG_RESULT = "DEBUG_RESULT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    WORKFLOW_UPDATE = "WORKFLOW_UPDATE"


class AgentMessage(BaseModel):
    """Structured and validated message passed between agents."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_agent_id: str
    receiver_agent_id: str
    workflow_id: str
    task_id: Optional[str] = None
    message_type: MessageType
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def to_summary(self) -> str:
        """Format an informative one-line summary of this message."""
        task_str = f" [Task: {self.task_id}]" if self.task_id else ""
        return (
            f"[{self.message_type.value}] {self.sender_agent_id} -> "
            f"{self.receiver_agent_id}{task_str} ({self.message_id[:8]})"
        )


class MessageSecurityError(Exception):
    """Raised when message validation or agent identity verification fails."""
    pass


class MessageBus:
    """In-process message bus providing synchronous or queued agent communication."""

    def __init__(self) -> None:
        """Initialize the message bus."""
        self._subscribers: Dict[str, List[Callable[[AgentMessage], None]]] = {}
        self._history: List[AgentMessage] = []

    def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """Register an agent subscriber callback for incoming messages."""
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = []
        self._subscribers[agent_id].append(callback)

    def unsubscribe(self, agent_id: str, callback: Optional[Callable[[AgentMessage], None]] = None) -> None:
        """Remove agent subscriber callback."""
        if agent_id in self._subscribers:
            if callback:
                self._subscribers[agent_id] = [c for c in self._subscribers[agent_id] if c != callback]
            else:
                self._subscribers[agent_id] = []

    def publish(self, message: AgentMessage, authenticated_sender_id: Optional[str] = None) -> None:
        """Validate and dispatch a message to the target agent or broadcast.

        Args:
            message: Validated AgentMessage instance.
            authenticated_sender_id: If provided, ensures the sender cannot impersonate another agent.
        """
        if authenticated_sender_id and message.sender_agent_id != authenticated_sender_id:
            raise MessageSecurityError(
                f"Agent impersonation rejected: Agent '{authenticated_sender_id}' "
                f"attempted to send message as '{message.sender_agent_id}'."
            )

        # Store in append-only history
        self._history.append(message)

        # Direct recipient dispatch
        target_id = message.receiver_agent_id
        if target_id == "*" or target_id == "ALL":
            for subs in self._subscribers.values():
                for cb in subs:
                    try:
                        cb(message)
                    except Exception:
                        pass
        elif target_id in self._subscribers:
            for cb in self._subscribers[target_id]:
                try:
                    cb(message)
                except Exception:
                    pass

    def get_history(
        self,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentMessage]:
        """Retrieve historical messages filtered by workflow or task."""
        filtered = self._history
        if workflow_id:
            filtered = [m for m in filtered if m.workflow_id == workflow_id]
        if task_id:
            filtered = [m for m in filtered if m.task_id == task_id]
        return filtered[-limit:]

    def clear(self) -> None:
        """Clear message history and subscribers."""
        self._history.clear()
        self._subscribers.clear()

