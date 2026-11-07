"""Permission manager enforcing user authorization boundaries for execution operations."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

from codeagent.config.settings import Settings, get_settings


class ExecutionPermissionError(Exception):
    """Base exception for execution authorization failures."""
    pass


class ExecutionNotApprovedError(ExecutionPermissionError):
    """Raised when an execution request is rejected by the user."""
    pass


class ExecutionDisabledError(ExecutionPermissionError):
    """Raised when execution capability is disabled by settings."""
    pass


@dataclass
class ExecutionPlan:
    """Description of an intended operation presented to the user for approval."""

    operation: str  # "python", "terminal", "dependency", "test"
    command: str
    working_directory: str
    details: dict = field(default_factory=dict)
    reason: Optional[str] = None

    def to_summary(self) -> str:
        """Format an informative summary of the proposed execution."""
        lines = [
            f"Operation: {self.operation.capitalize()}",
            f"Command:   {self.command}",
            f"Working Dir: {self.working_directory}",
        ]
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            lines.append(f"Details:     {detail_str}")
        if self.reason:
            lines.append(f"Purpose:     {self.reason}")
        return "\n".join(lines)


class PermissionManager:
    """Determines authorization requirements and coordinates user approval dialogs."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        approval_callback: Optional[Callable[[ExecutionPlan], bool]] = None,
    ) -> None:
        """Initialize PermissionManager.

        Args:
            settings: Settings configuration instance.
            approval_callback: Optional callback receiving ExecutionPlan and returning bool.
        """
        self.settings = settings or get_settings()
        self.approval_callback = approval_callback

    def is_approval_required(self, operation: str) -> bool:
        """Check whether an operation requires user approval based on configuration.

        Args:
            operation: Type of operation ("python", "terminal", "dependency", "test").

        Returns:
            bool: True if approval is required.
        """
        if not self.settings.execution_enabled:
            raise ExecutionDisabledError(
                "Execution capability is disabled by EXECUTION_ENABLED=false setting."
            )

        op = operation.lower()
        if op == "dependency":
            # Dependency installation ALWAYS requires approval by policy
            return True
        elif op == "python":
            return self.settings.require_python_approval
        elif op == "terminal":
            return self.settings.require_command_approval
        elif op == "test":
            # Running tests does not require approval unless command approval is strict
            return False
        return True

    def check_and_request_approval(
        self,
        plan: ExecutionPlan,
        bypass_approval: bool = False,
    ) -> bool:
        """Evaluate authorization and request human user approval if necessary.

        Args:
            plan: The proposed ExecutionPlan.
            bypass_approval: Explicit parameter bypass (only allowed if policy permits).

        Returns:
            bool: True if approved.

        Raises:
            ExecutionDisabledError: If execution is disabled.
            ExecutionNotApprovedError: If approval is rejected or not granted.
        """
        if not self.settings.execution_enabled:
            raise ExecutionDisabledError(
                "Execution capability is disabled by EXECUTION_ENABLED=false setting."
            )

        required = self.is_approval_required(plan.operation)

        if not required:
            return True

        if bypass_approval and plan.operation != "dependency":
            return True

        if self.approval_callback:
            approved = self.approval_callback(plan)
            if approved:
                return True

        raise ExecutionNotApprovedError(
            f"Execution of '{plan.command}' ({plan.operation}) was rejected or not approved by user."
        )

