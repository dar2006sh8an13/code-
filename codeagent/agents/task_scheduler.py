"""Task scheduling, dependency graph resolution, cycle detection, and priority dispatching."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import uuid
from pydantic import BaseModel, Field

from codeagent.agents.base_agent import AgentRole


class TaskStatus(str, Enum):
    """Lifecycle states for workflow tasks."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class DependencyCycleError(Exception):
    """Raised when a circular dependency is detected in the task graph."""

    def __init__(self, message: str, cycle: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.cycle = cycle or []


class WorkflowTask(BaseModel):
    """Individual unit of work assigned to an autonomous agent within a workflow."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    workflow_id: str
    name: str
    description: str = ""
    assigned_agent: AgentRole = AgentRole.CODER
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5  # 1 (lowest) to 10 (highest)
    dependencies: List[str] = Field(default_factory=list)
    required_input: Dict[str, Any] = Field(default_factory=dict)
    expected_output: Dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: List[str] = Field(default_factory=list)
    risk_level: str = "LOW"
    estimated_complexity: str = "LOW"
    retry_count: int = 0
    max_retries: int = 2
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_summary(self) -> str:
        """Format a concise overview of the task."""
        dep_str = f" (deps: {', '.join(self.dependencies)})" if self.dependencies else ""
        return f"[{self.status.value}] {self.task_id}: {self.name} -> {self.assigned_agent.value} (P{self.priority}){dep_str}"


class TaskScheduler:
    """Manages Directed Acyclic Graph (DAG) dependencies and prioritizes task scheduling."""

    def __init__(self, workflow_id: str) -> None:
        """Initialize scheduler for a specific workflow."""
        self.workflow_id = workflow_id
        self._tasks: Dict[str, WorkflowTask] = {}

    def add_task(self, task: WorkflowTask) -> None:
        """Add a task to the schedule and validate graph integrity."""
        if task.task_id in self._tasks:
            raise ValueError(f"Task with ID '{task.task_id}' already registered.")
        self._tasks[task.task_id] = task
        # Validate that graph remains acyclic
        self.detect_cycles()

    def get_task(self, task_id: str) -> Optional[WorkflowTask]:
        """Lookup task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[WorkflowTask]:
        """Return all tasks in scheduler."""
        return list(self._tasks.values())

    def detect_cycles(self) -> List[str]:
        """Detect circular dependencies using Depth First Search (DFS).

        Returns:
            List[str]: Detected cycle path, or empty list if graph is acyclic.

        Raises:
            DependencyCycleError: If a cycle is present in the task dependencies.
        """
        # Graph: task_id -> set of dependency task_ids
        adj: Dict[str, List[str]] = {tid: t.dependencies for tid, t in self._tasks.items()}
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        parent_path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            visited[node] = 1
            parent_path.append(node)

            for dep in adj.get(node, []):
                # If dependency points to a task not yet registered, it's an external/forward ref
                if dep not in self._tasks:
                    continue
                if visited.get(dep, 0) == 1:
                    # Cycle found!
                    idx = parent_path.index(dep)
                    cycle = parent_path[idx:] + [dep]
                    return cycle
                elif visited.get(dep, 0) == 0:
                    c = dfs(dep)
                    if c:
                        return c

            parent_path.pop()
            visited[node] = 2
            return None

        for tid in self._tasks:
            if visited.get(tid, 0) == 0:
                cycle_found = dfs(tid)
                if cycle_found:
                    cycle_str = " -> ".join(cycle_found)
                    raise DependencyCycleError(
                        f"Circular dependency detected in workflow '{self.workflow_id}': {cycle_str}",
                        cycle=cycle_found,
                    )

        return []

    def get_ready_tasks(self) -> List[WorkflowTask]:
        """Identify all tasks ready to run (PENDING, all dependencies COMPLETED).

        Returns:
            List[WorkflowTask] ordered by priority descending.
        """
        ready: List[WorkflowTask] = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            # Check all dependencies
            deps_satisfied = True
            for dep_id in task.dependencies:
                dep_task = self._tasks.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                ready.append(task)

        # Sort by priority descending (10 down to 1)
        ready.sort(key=lambda t: t.priority, reverse=True)
        return ready

    def mark_running(self, task_id: str) -> None:
        """Update task status to RUNNING."""
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc).isoformat()

    def mark_completed(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> None:
        """Update task status to COMPLETED and update ready status of dependents."""
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.result = result or {}
            task.completed_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, task_id: str, error: str) -> None:
        """Mark task as FAILED and cascade BLOCKED status to all dependents."""
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.now(timezone.utc).isoformat()
            self._cascade_blocked(task_id)

    def mark_blocked(self, task_id: str, reason: str) -> None:
        """Mark task as BLOCKED."""
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.BLOCKED
            task.error = reason
            self._cascade_blocked(task_id)

    def mark_cancelled(self, task_id: str) -> None:
        """Mark task as CANCELLED."""
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            self._cascade_blocked(task_id)

    def _cascade_blocked(self, failed_task_id: str) -> None:
        """Recursively mark all tasks depending on failed_task_id as BLOCKED."""
        for task in self._tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.READY):
                if failed_task_id in task.dependencies:
                    task.status = TaskStatus.BLOCKED
                    task.error = f"Blocked by dependency '{failed_task_id}'"
                    # Recurse
                    self._cascade_blocked(task.task_id)

    def is_workflow_complete(self) -> bool:
        """Return True if all tasks are in a terminal state."""
        terminal_states = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED}
        return all(t.status in terminal_states for t in self._tasks.values())

    def has_failed_tasks(self) -> bool:
        """Check if any task in the workflow failed or is blocked."""
        return any(t.status in (TaskStatus.FAILED, TaskStatus.BLOCKED) for t in self._tasks.values())

