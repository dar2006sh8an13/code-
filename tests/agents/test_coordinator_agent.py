"""Unit tests for CoordinatorAgent, multi-agent orchestration, retries, and cancellation."""

from codeagent.agents.agent_factory import AgentFactory
from codeagent.agents.coordinator_agent import CoordinatorAgent, CoordinatorInput
from codeagent.agents.workflow_state import WorkflowStatus
from codeagent.config.settings import Settings


def test_coordinator_end_to_end_sequential_workflow(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path), WORKFLOW_STORAGE_PATH="data/workflows")
    factory = AgentFactory(workspace_root=tmp_path, settings=settings)
    coord = factory.build_full_system()

    inp = CoordinatorInput(
        user_goal="Build user profile helper",
        workflow_type="BUILD_PROJECT",
        auto_review=True,
    )

    out = coord.execute(inp)
    assert out.status == WorkflowStatus.COMPLETED
    assert out.tasks_completed == out.tasks_total
    assert out.tasks_failed == 0
    assert out.review_verdict == "APPROVED"
    assert len(out.task_summaries) >= 3


def test_coordinator_workflow_cancellation(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    factory = AgentFactory(workspace_root=tmp_path, settings=settings)
    coord = factory.build_full_system()

    # Cancel before execution
    coord.cancel()

    inp = CoordinatorInput(
        user_goal="Cancelled task",
        workflow_type="BUILD_PROJECT",
    )

    out = coord.execute(inp)
    assert out.status == WorkflowStatus.CANCELLED

