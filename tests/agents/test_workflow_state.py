"""Unit tests for WorkflowStateManager SQLite WAL persistence and queries."""

import pytest
from codeagent.agents.agent_messages import AgentMessage, MessageType
from codeagent.agents.base_agent import AgentRole
from codeagent.agents.task_scheduler import TaskStatus, WorkflowTask
from codeagent.agents.workflow_state import (
    ReviewDecision,
    ReviewFinding,
    ReviewRecord,
    WorkflowRecord,
    WorkflowStateManager,
    WorkflowStatus,
)


def test_workflow_state_crud(tmp_path):
    mgr = WorkflowStateManager(workspace_root=tmp_path)

    # 1. Save and retrieve workflow
    wf = WorkflowRecord(
        workflow_id="wf_001",
        user_task="Build authentication endpoint",
        workflow_type="BUILD_PROJECT",
        status=WorkflowStatus.RUNNING,
    )
    mgr.save_workflow(wf)

    loaded = mgr.get_workflow("wf_001")
    assert loaded is not None
    assert loaded.workflow_id == "wf_001"
    assert loaded.status == WorkflowStatus.RUNNING

    # 2. Save tasks
    t1 = WorkflowTask(
        task_id="t1",
        workflow_id="wf_001",
        name="Write models",
        assigned_agent=AgentRole.CODER,
        status=TaskStatus.COMPLETED,
    )
    mgr.save_task(t1)

    tasks = mgr.get_tasks_for_workflow("wf_001")
    assert len(tasks) == 1
    assert tasks[0].name == "Write models"

    # 3. Save review
    rev = ReviewRecord(
        workflow_id="wf_001",
        task_id="t1",
        reviewer_agent_id="rev_1",
        decision=ReviewDecision.APPROVED,
        findings=[
            ReviewFinding(category="Quality", severity="LOW", description="Good code structure")
        ],
        summary="Approved",
    )
    mgr.save_review(rev)

    reviews = mgr.get_reviews_for_task("t1")
    assert len(reviews) == 1
    assert reviews[0].decision == ReviewDecision.APPROVED
    assert len(reviews[0].findings) == 1

    # 4. Save audit message
    msg = AgentMessage(
        sender_agent_id="planner_1",
        receiver_agent_id="coord_1",
        workflow_id="wf_001",
        task_id="t1",
        message_type=MessageType.TASK_COMPLETED,
    )
    mgr.save_message(msg)

    # 5. Cancel workflow
    assert mgr.cancel_workflow("wf_001", reason="Manual abort") is True
    cancelled_wf = mgr.get_workflow("wf_001")
    assert cancelled_wf.status == WorkflowStatus.CANCELLED
    assert cancelled_wf.error == "Manual abort"

