"""Base agent abstract class, status enums, role definitions, and context container."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar
import uuid
from pydantic import BaseModel, ConfigDict, Field

from codeagent.config.settings import Settings, get_settings
from codeagent.tools.registry import ToolRegistry


class AgentRole(str, Enum):
    """Core specialized agent roles."""

    PLANNER = "planner"
    CODER = "coder"
    CODE = "code"
    DEBUGGER = "debugger"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"


class AgentStatus(str, Enum):
    """Execution status for an individual agent."""

    IDLE = "idle"
    BUSY = "busy"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentContext(BaseModel):
    """Shared contextual environment passed to an agent during task execution."""

    workflow_id: str
    task_id: Optional[str] = None
    workspace_root: str
    project_id: Optional[str] = None
    step_number: int = 1
    shared_state: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


InT = TypeVar("InT", bound=BaseModel)
OutT = TypeVar("OutT", bound=BaseModel)


class BaseAgent(ABC):
    """Abstract base class establishing the interface and contract for all Code AG agents."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: str = "BaseAgent",
        role: AgentRole = AgentRole.COORDINATOR,
        description: str = "Base autonomous agent",
        system_instructions: str = "",
        capabilities: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        input_schema: Optional[Type[BaseModel]] = None,
        output_schema: Optional[Type[BaseModel]] = None,
        timeout_seconds: float = 300.0,
        settings: Optional[Settings] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        """Initialize the base agent."""
        self.agent_id: str = agent_id or f"{role.value}_{uuid.uuid4().hex[:8]}"
        self.name: str = name
        self.role: AgentRole = role
        self.description: str = description
        self.system_instructions: str = system_instructions
        self.capabilities: List[str] = capabilities or []
        self.tools: List[str] = tools or []
        self.input_schema: Type[BaseModel] = input_schema or BaseModel
        self.output_schema: Type[BaseModel] = output_schema or BaseModel
        self.timeout_seconds: float = timeout_seconds
        self.settings: Settings = settings or get_settings()
        self.tool_registry: Optional[ToolRegistry] = tool_registry

        self.status: AgentStatus = AgentStatus.IDLE
        self._cancelled: bool = False
        self._last_error: Optional[str] = None
        self._created_at: str = datetime.now(timezone.utc).isoformat()
        self._initialized: bool = False

    def initialize(self) -> None:
        """Perform initialization and setup before execution."""
        self.status = AgentStatus.IDLE
        self._cancelled = False
        self._last_error = None
        self._initialized = True

    def validate_input(self, input_data: Any) -> BaseModel:
        """Validate raw or parsed input against the declared input schema."""
        if isinstance(input_data, self.input_schema):
            return input_data
        if isinstance(input_data, dict):
            return self.input_schema.model_validate(input_data)
        if isinstance(input_data, str):
            return self.input_schema.model_validate_json(input_data)
        raise ValueError(
            f"Input data of type {type(input_data).__name__} cannot be validated against {self.input_schema.__name__}"
        )

    def validate_output(self, output_data: Any) -> BaseModel:
        """Validate output payload against declared output schema."""
        if isinstance(output_data, self.output_schema):
            return output_data
        if isinstance(output_data, dict):
            return self.output_schema.model_validate(output_data)
        if isinstance(output_data, str):
            return self.output_schema.model_validate_json(output_data)
        raise ValueError(
            f"Output data of type {type(output_data).__name__} cannot be validated against {self.output_schema.__name__}"
        )

    def get_status(self) -> AgentStatus:
        """Return the current agent status."""
        return self.status

    def cancel(self) -> None:
        """Request immediate cancellation of the agent's active execution."""
        self._cancelled = True
        self.status = AgentStatus.CANCELLED

    def reset(self) -> None:
        """Reset agent to idle state and clear errors."""
        self.status = AgentStatus.IDLE
        self._cancelled = False
        self._last_error = None

    @abstractmethod
    def execute(self, input_data: Any, context: Optional[AgentContext] = None) -> BaseModel:
        """Execute the agent's core specialized task synchronously."""
        pass

    def to_info_dict(self) -> Dict[str, Any]:
        """Return metadata summary for agent inspection."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "tools": self.tools,
            "input_schema": self.input_schema.__name__,
            "output_schema": self.output_schema.__name__,
            "timeout_seconds": self.timeout_seconds,
            "initialized": self._initialized,
        }
