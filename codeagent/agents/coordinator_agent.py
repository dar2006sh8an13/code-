"""Coordinator agent: orchestrates multi-agent task execution, review loops, and workflows."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from codeagent.agents.agent_messages import AgentMessage, MessageBus, MessageType
from codeagent.agents.agent_registry import AgentRegistry
from codeagent.agents.base_agent import AgentContext, AgentRole, AgentStatus, BaseAgent
from codeagent.agents.coder_agent import CoderInput, CoderOutput
from codeagent.agents.debugger_agent import DebuggerInput, DebuggerOutput
from codeagent.agents.file_locks import FileLockManager
from codeagent.agents.planner_agent import PlannerInput, PlannerOutput
from codeagent.agents.reviewer_agent import ReviewerInput, ReviewerOutput
from codeagent.agents.task_scheduler import TaskScheduler, TaskStatus, WorkflowTask
from codeagent.agents.workflow_state import (
    ReviewDecision,
    ReviewRecord,
    WorkflowRecord,
    WorkflowStateManager,
    WorkflowStatus,
)
from codeagent.config.settings import Settings, get_settings


class CoordinatorInput(BaseModel):
    """Input payload initiating multi-agent workflow execution."""

    user_goal: str
    workflow_type: str = "BUILD_PROJECT"
    workflow_id: Optional[str] = None
    max_parallel_agents: int = 2
    auto_review: bool = True


class CoordinatorOutput(BaseModel):
    """Final comprehensive report from coordinated multi-agent workflow."""

    workflow_id: str
    status: WorkflowStatus
    user_goal: str
    workflow_type: str
    tasks_total: int
    tasks_completed: int
    tasks_failed: int
    review_verdict: Optional[str] = None
    summary: str
    execution_duration_seconds: float = 0.0
    task_summaries: List[Dict[str, Any]] = Field(default_factory=list)


class CoordinatorAgent(BaseAgent):
    """Central deterministic workflow coordinator orchestrating Planner, Code, Debugger, and Reviewer."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        registry: Optional[AgentRegistry] = None,
        message_bus: Optional[MessageBus] = None,
        state_manager: Optional[WorkflowStateManager] = None,
        file_lock_manager: Optional[FileLockManager] = None,
        workspace_root: Optional[Path] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize CoordinatorAgent."""
        cfg = settings or get_settings()
        super().__init__(
            agent_id=agent_id or f"coordinator_{uuid.uuid4().hex[:8]}",
            name="CoordinatorAgent",
            role=AgentRole.COORDINATOR,
            description="Centrally orchestrates multi-agent tasks, dependency scheduling, reviews, and recovery",
            system_instructions=(
                "You are the Coordinator Agent. You direct workflow execution deterministically. "
                "Enforce task dependencies, request reviews, handle retries, and respect safety bounds. "
                "Do not bypass file approvals or execute arbitrary shell commands."
            ),
            capabilities=["workflow_orchestration", "dependency_scheduling", "parallel_execution", "review_rework_loop", "recovery"],
            tools=["task_assignment", "workflow_state", "agent_dispatch", "cancellation"],
            input_schema=CoordinatorInput,
            output_schema=CoordinatorOutput,
            settings=cfg,
        )
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.registry = registry or AgentRegistry()
        self.message_bus = message_bus or MessageBus()
        self.state_manager = state_manager or WorkflowStateManager(
            workspace_root=self.workspace_root,
            storage_path=cfg.workflow_storage_path,
        )
        self.file_locks = file_lock_manager or FileLockManager(workspace_root=self.workspace_root)
        self._current_scheduler: Optional[TaskScheduler] = None
        self._active_workflow_id: Optional[str] = None

    def execute(self, input_data: Any, context: Optional[AgentContext] = None) -> CoordinatorOutput:
        """Synchronous entry point that runs the coordinated workflow to completion."""
        coord_in = self.validate_input(input_data)
        assert isinstance(coord_in, CoordinatorInput)
        return self._run_coordination_workflow(coord_in)

    def _run_coordination_workflow(self, coord_in: CoordinatorInput) -> CoordinatorOutput:
        """Coordination engine driving the DAG of tasks to completion with thread concurrency."""
        import concurrent.futures
        start_time = time.time()
        self.status = AgentStatus.BUSY
        workflow_id = coord_in.workflow_id or f"wf_{uuid.uuid4().hex[:8]}"
        self._active_workflow_id = workflow_id

        # 1. Initialize persistent record
        wf_record = WorkflowRecord(
            workflow_id=workflow_id,
            user_task=coord_in.user_goal,
            workflow_type=coord_in.workflow_type,
            status=WorkflowStatus.RUNNING,
            start_time=datetime.now(timezone.utc).isoformat(),
        )
        self.state_manager.save_workflow(wf_record)

        # 2. Request Plan from Planner Agent
        planner = self.registry.get_primary_agent(AgentRole.PLANNER)
        if not planner:
            err_msg = "Planner agent is not registered in the system."
            wf_record.status = WorkflowStatus.FAILED
            wf_record.error = err_msg
            wf_record.end_time = datetime.now(timezone.utc).isoformat()
            self.state_manager.save_workflow(wf_record)
            self.status = AgentStatus.FAILED
            return CoordinatorOutput(
                workflow_id=workflow_id,
                status=WorkflowStatus.FAILED,
                user_goal=coord_in.user_goal,
                workflow_type=coord_in.workflow_type,
                tasks_total=0,
                tasks_completed=0,
                tasks_failed=1,
                summary=err_msg,
            )

        self._publish_message(
            sender=self.agent_id,
            receiver=planner.agent_id,
            wf_id=workflow_id,
            msg_type=MessageType.TASK_ASSIGNMENT,
            payload={"goal": coord_in.user_goal, "type": coord_in.workflow_type},
        )

        plan_res = planner.execute(
            PlannerInput(
                goal=coord_in.user_goal,
                workflow_type=coord_in.workflow_type,
            ),
            context=AgentContext(workflow_id=workflow_id, workspace_root=str(self.workspace_root)),
        )
        assert isinstance(plan_res, PlannerOutput)

        # 3. Register tasks in scheduler and persistent state
        scheduler = TaskScheduler(workflow_id=workflow_id)
        self._current_scheduler = scheduler

        for t_spec in plan_res.tasks:
            role_val = AgentRole.CODER
            if t_spec.assigned_agent.lower() == "debugger":
                role_val = AgentRole.DEBUGGER
            elif t_spec.assigned_agent.lower() == "reviewer":
                role_val = AgentRole.REVIEWER

            wf_task = WorkflowTask(
                task_id=t_spec.task_id,
                workflow_id=workflow_id,
                name=t_spec.task_name,
                description=t_spec.description,
                assigned_agent=role_val,
                priority=t_spec.priority,
                dependencies=t_spec.dependencies,
                required_input=t_spec.required_input,
                expected_output=t_spec.expected_output,
                acceptance_criteria=t_spec.acceptance_criteria,
                risk_level=t_spec.risk_level,
                estimated_complexity=t_spec.estimated_complexity,
                max_retries=self.settings.max_agent_retries,
            )
            scheduler.add_task(wf_task)
            self.state_manager.save_task(wf_task)

        # 4. Process Tasks via Dependency Graph
        concurrency = min(coord_in.max_parallel_agents, self.settings.max_parallel_agents)
        last_review_verdict = None

        def _execute_single_task(task: WorkflowTask) -> None:
            nonlocal last_review_verdict
            scheduler.mark_running(task.task_id)
            self.state_manager.save_task(task)

            target_agent = self.registry.get_primary_agent(task.assigned_agent)
            if not target_agent:
                scheduler.mark_failed(task.task_id, f"No agent registered for role '{task.assigned_agent.value}'.")
                self.state_manager.save_task(task)
                return

            # Execute task with retry policy
            success = False
            err_msg = ""
            res_dict = {}

            while task.retry_count <= task.max_retries and not success:
                try:
                    ctx = AgentContext(
                        workflow_id=workflow_id,
                        task_id=task.task_id,
                        workspace_root=str(self.workspace_root),
                    )

                    if task.assigned_agent == AgentRole.CODER:
                        out = target_agent.execute(
                            CoderInput(
                                task_id=task.task_id,
                                task_name=task.name,
                                description=task.description,
                                instructions=task.description,
                            ),
                            context=ctx,
                        )
                        assert isinstance(out, CoderOutput)
                        success = out.success
                        res_dict = out.model_dump()
                        if not success:
                            err_msg = out.changes_summary

                        # Review and rework loop
                        if success and coord_in.auto_review:
                            rev_agent = self.registry.get_primary_agent(AgentRole.REVIEWER)
                            if rev_agent:
                                review_out = rev_agent.execute(
                                    ReviewerInput(
                                        task_id=task.task_id,
                                        task_name=task.name,
                                        files_to_review=out.files_created + out.files_modified,
                                        test_results=out.test_summary,
                                    ),
                                    context=ctx,
                                )
                                assert isinstance(review_out, ReviewerOutput)
                                last_review_verdict = review_out.decision.value

                                self.state_manager.save_review(
                                    ReviewRecord(
                                        workflow_id=workflow_id,
                                        task_id=task.task_id,
                                        reviewer_agent_id=rev_agent.agent_id,
                                        decision=review_out.decision,
                                        severity=review_out.severity,
                                        findings=review_out.findings,
                                        evidence=review_out.evidence,
                                        recommended_changes=review_out.recommended_changes,
                                        summary=review_out.summary,
                                    )
                                )

                                if review_out.decision == ReviewDecision.REJECTED:
                                    success = False
                                    err_msg = f"Rejected by Reviewer: {review_out.summary}"

                    elif task.assigned_agent == AgentRole.DEBUGGER:
                        out = target_agent.execute(
                            DebuggerInput(
                                task_id=task.task_id,
                                error_text=task.description,
                            ),
                            context=ctx,
                        )
                        assert isinstance(out, DebuggerOutput)
                        success = out.success
                        res_dict = out.model_dump()
                        if not success:
                            err_msg = out.summary

                    elif task.assigned_agent == AgentRole.REVIEWER:
                        out = target_agent.execute(
                            ReviewerInput(
                                task_id=task.task_id,
                                task_name=task.name,
                                description=task.description,
                            ),
                            context=ctx,
                        )
                        assert isinstance(out, ReviewerOutput)
                        success = out.decision in (ReviewDecision.APPROVED, ReviewDecision.NEEDS_REVISION)
                        res_dict = out.model_dump()
                        last_review_verdict = out.decision.value
                        if not success:
                            err_msg = out.summary

                except Exception as exc:
                    success = False
                    err_msg = str(exc)

                if not success:
                    task.retry_count += 1
                    if task.retry_count <= task.max_retries:
                        time.sleep(0.05)

            if success:
                scheduler.mark_completed(task.task_id, result=res_dict)
            else:
                scheduler.mark_failed(task.task_id, error=err_msg or "Task failed after retries.")
            self.state_manager.save_task(task)

        while not scheduler.is_workflow_complete():
            if self._cancelled:
                wf_record.status = WorkflowStatus.CANCELLED
                wf_record.error = "Workflow cancelled by coordinator request."
                break

            ready_tasks = scheduler.get_ready_tasks()
            if not ready_tasks:
                if scheduler.has_failed_tasks():
                    break
                # No ready tasks and not finished -> deadlock / blocked
                for t in scheduler.list_tasks():
                    if t.status == TaskStatus.PENDING:
                        scheduler.mark_blocked(t.task_id, "Dependencies blocked or missing.")
                        self.state_manager.save_task(t)
                break

            # Execute ready tasks (concurrency >= 2 uses ThreadPoolExecutor, 1 uses direct execution)
            if len(ready_tasks) > 1 and concurrency > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(concurrency, len(ready_tasks))) as executor:
                    futures = [executor.submit(_execute_single_task, t) for t in ready_tasks]
                    concurrent.futures.wait(futures)
            else:
                for t in ready_tasks:
                    _execute_single_task(t)

        # 5. Final Workflow State Reconciliation
        duration = round(time.time() - start_time, 2)
        all_tasks = scheduler.list_tasks()
        completed_count = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
        failed_count = sum(1 for t in all_tasks if t.status in (TaskStatus.FAILED, TaskStatus.BLOCKED))

        if failed_count > 0:
            wf_record.status = WorkflowStatus.FAILED
            wf_record.error = f"{failed_count} task(s) failed or were blocked."
            self.status = AgentStatus.FAILED
        elif self._cancelled:
            wf_record.status = WorkflowStatus.CANCELLED
            self.status = AgentStatus.CANCELLED
        else:
            wf_record.status = WorkflowStatus.COMPLETED
            self.status = AgentStatus.COMPLETED

        wf_record.end_time = datetime.now(timezone.utc).isoformat()
        self.state_manager.save_workflow(wf_record)

        summary_text = (
            f"Workflow {wf_record.status.value}: {completed_count}/{len(all_tasks)} tasks completed "
            f"in {duration}s. Review decision: {last_review_verdict or 'N/A'}."
        )

        return CoordinatorOutput(
            workflow_id=workflow_id,
            status=wf_record.status,
            user_goal=coord_in.user_goal,
            workflow_type=coord_in.workflow_type,
            tasks_total=len(all_tasks),
            tasks_completed=completed_count,
            tasks_failed=failed_count,
            review_verdict=last_review_verdict,
            summary=summary_text,
            execution_duration_seconds=duration,
            task_summaries=[
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "agent": t.assigned_agent.value,
                    "status": t.status.value,
                    "retries": t.retry_count,
                    "error": t.error,
                }
                for t in all_tasks
            ],
        )

    def _publish_message(
        self,
        sender: str,
        receiver: str,
        wf_id: str,
        msg_type: MessageType,
        payload: Dict[str, Any],
        task_id: Optional[str] = None,
    ) -> None:
        """Publish and record an audit message on the message bus."""
        msg = AgentMessage(
            sender_agent_id=sender,
            receiver_agent_id=receiver,
            workflow_id=wf_id,
            task_id=task_id,
            message_type=msg_type,
            payload=payload,
        )
        self.message_bus.publish(msg, authenticated_sender_id=sender)
        self.state_manager.save_message(msg)

    def cancel(self) -> None:
        """Cancel the active workflow execution."""
        super().cancel()
        if self._active_workflow_id:
            self.state_manager.cancel_workflow(self._active_workflow_id)
        if self._current_scheduler:
            for t in self._current_scheduler.list_tasks():
                if t.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING):
                    self._current_scheduler.mark_cancelled(t.task_id)
                    self.state_manager.save_task(t)
