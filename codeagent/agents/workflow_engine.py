"""Workflow engine coordinating execution, timeouts, cancellation, and recovery across templates."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from codeagent.agents.agent_factory import AgentFactory
from codeagent.agents.coordinator_agent import CoordinatorAgent, CoordinatorInput, CoordinatorOutput
from codeagent.agents.task_scheduler import WorkflowTask
from codeagent.agents.workflow_state import WorkflowRecord, WorkflowStateManager, WorkflowStatus
from codeagent.agents.workflow_templates import WorkflowType, get_template
from codeagent.config.settings import Settings, get_settings


class WorkflowEngine:
    """High-level orchestration engine executing, tracking, and resuming multi-agent workflows."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        settings: Optional[Settings] = None,
        agent_factory: Optional[AgentFactory] = None,
    ) -> None:
        """Initialize WorkflowEngine."""
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.settings = settings or get_settings()
        self.factory = agent_factory or AgentFactory(
            workspace_root=self.workspace_root,
            settings=self.settings,
        )
        self.coordinator = self.factory.build_full_system()
        self.state_manager = self.factory.state_manager

    def run_workflow(
        self,
        goal: str,
        workflow_type: WorkflowType = WorkflowType.BUILD_PROJECT,
        workflow_id: Optional[str] = None,
        max_parallel_agents: Optional[int] = None,
    ) -> CoordinatorOutput:
        """Execute a full multi-agent workflow based on template or custom goal."""
        template = get_template(workflow_type)
        parallel = max_parallel_agents or self.settings.max_parallel_agents

        coord_in = CoordinatorInput(
            user_goal=goal,
            workflow_type=template.template_type.value,
            workflow_id=workflow_id,
            max_parallel_agents=parallel,
            auto_review=True,
        )
        return self.coordinator.execute(coord_in)

    def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowRecord]:
        """Fetch current status of a workflow from persistent state."""
        return self.state_manager.get_workflow(workflow_id)

    def list_workflows(self, limit: int = 50) -> List[WorkflowRecord]:
        """List past and active workflows."""
        return self.state_manager.list_workflows(limit=limit)

    def get_task(self, task_id: str) -> Optional[WorkflowTask]:
        """Lookup task details by ID."""
        # Query task across workflows
        with self.state_manager._get_connection() as conn:
            row = conn.execute(
                "SELECT workflow_id FROM workflow_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if not row:
                return None
            wf_id = row["workflow_id"]
            tasks = self.state_manager.get_tasks_for_workflow(wf_id)
            for t in tasks:
                if t.task_id == task_id:
                    return t
        return None

    def list_tasks_for_workflow(self, workflow_id: str) -> List[WorkflowTask]:
        """Fetch all tasks in a specific workflow."""
        return self.state_manager.get_tasks_for_workflow(workflow_id)

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow."""
        self.coordinator.cancel()
        return self.state_manager.cancel_workflow(workflow_id)

    def resume_workflow(self, workflow_id: str) -> Optional[CoordinatorOutput]:
        """Resume an interrupted eligible workflow.

        Rule: Do NOT automatically resume workflows containing expired approvals.
        Do NOT repeat completed destructive actions after a restart.
        """
        wf = self.state_manager.resume_workflow(workflow_id)
        if not wf:
            return None

        # Re-run remaining tasks
        coord_in = CoordinatorInput(
            user_goal=wf.user_task,
            workflow_type=wf.workflow_type,
            workflow_id=wf.workflow_id,
            max_parallel_agents=self.settings.max_parallel_agents,
        )
        return self.coordinator.execute(coord_in)

