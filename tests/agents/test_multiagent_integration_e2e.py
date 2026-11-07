"""Comprehensive end-to-end integration test exercising all five core agents in an isolated temporary project."""

from pathlib import Path
from codeagent.agents.agent_factory import AgentFactory
from codeagent.agents.coder_agent import CoderInput
from codeagent.agents.coordinator_agent import CoordinatorInput
from codeagent.agents.debugger_agent import DebuggerInput
from codeagent.agents.reviewer_agent import ReviewerInput
from codeagent.agents.workflow_engine import WorkflowEngine
from codeagent.agents.workflow_state import ReviewDecision, WorkflowStatus
from codeagent.agents.workflow_templates import WorkflowType
from codeagent.config.settings import Settings


def test_multiagent_integration_e2e_full_lifecycle(tmp_path):
    """End-to-end multi-agent test: Planner -> Coordinator -> Coder -> Debugger -> Reviewer."""
    # 1. Setup isolated temporary project workspace
    settings = Settings(
        WORKSPACE_ROOT=str(tmp_path),
        WORKFLOW_STORAGE_PATH="data/workflows",
        AUDIT_STORAGE_PATH="data/audit",
        BACKUP_STORAGE_PATH="data/backups",
    )
    engine = WorkflowEngine(workspace_root=tmp_path, settings=settings)
    factory = engine.factory

    # 2. Step 1: Submit a project task to WorkflowEngine
    res = engine.run_workflow(
        goal="Develop math calculation utility and run tests",
        workflow_type=WorkflowType.BUILD_PROJECT,
    )

    # 3. Step 2 & 3: Verify Planner decomposition and Coordinator scheduling
    assert res.status == WorkflowStatus.COMPLETED
    assert res.tasks_total >= 3
    assert res.tasks_completed == res.tasks_total
    assert res.tasks_failed == 0

    # 4. Step 4: Exercise Coder writing real files to disk
    coder = factory.create_coder()
    math_code = (
        "def compute_average(values: list[float]) -> float:\n"
        "    if not values:\n"
        "        return 0.0\n"
        "    return sum(values) / len(values)\n"
    )
    coder_out = coder.execute(
        CoderInput(
            task_id="coder_task_1",
            task_name="Write compute_average",
            description="Create math_service.py",
            files_to_create={"math_service.py": math_code},
        )
    )
    assert coder_out.success is True
    assert (tmp_path / "math_service.py").exists()

    # 5. Step 5: Exercise Debugger diagnosing an intentional error
    debugger = factory.create_debugger()
    err_text = (
        "Traceback (most recent call last):\n"
        "  File 'math_service.py', line 4, in compute_average\n"
        "ZeroDivisionError: division by zero\n"
    )
    dbg_out = debugger.execute(
        DebuggerInput(
            task_id="dbg_task_1",
            error_text=err_text,
            target_file="math_service.py",
        )
    )
    assert dbg_out.root_cause_type == "ZeroDivisionError"
    assert dbg_out.confidence_level.value in ("CONFIRMED", "LIKELY")

    # 6. Step 6 & 7: Exercise Reviewer independently inspecting actual changes
    reviewer = factory.create_reviewer()
    rev_out = reviewer.execute(
        ReviewerInput(
            task_id="rev_task_1",
            task_name="Review math_service",
            files_to_review=["math_service.py"],
            test_results={"passed": 1, "failed": 0},
        )
    )
    assert rev_out.decision == ReviewDecision.APPROVED

    # 7. Step 8: Verify persistent state recorded in SQLite
    status_rec = engine.get_workflow_status(res.workflow_id)
    assert status_rec is not None
    assert status_rec.status == WorkflowStatus.COMPLETED

    tasks = engine.list_tasks_for_workflow(res.workflow_id)
    assert len(tasks) == res.tasks_total

