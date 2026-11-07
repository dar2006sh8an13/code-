"""Unit tests for PlannerAgent, task decomposition, and plan schema validation."""

from codeagent.agents.base_agent import AgentRole
from codeagent.agents.planner_agent import PlannerAgent, PlannerInput, PlannerOutput


def test_planner_fallback_plan_decomposition():
    planner = PlannerAgent()
    inp = PlannerInput(goal="Add user login endpoint", workflow_type="ADD_FEATURE")

    out = planner.execute(inp)
    assert isinstance(out, PlannerOutput)
    assert len(out.tasks) >= 3

    # Verify task attributes
    task_names = [t.task_name for t in out.tasks]
    assert any("Core" in name or "Implement" in name for name in task_names)
    assert any("Review" in name for name in task_names)

    # Verify priorities and dependencies
    assert all(1 <= t.priority <= 10 for t in out.tasks)
    assert out.tasks[0].dependencies == []
    assert len(out.tasks[1].dependencies) > 0


def test_planner_bugfix_plan():
    planner = PlannerAgent()
    inp = PlannerInput(goal="Fix ZeroDivisionError in math_util.py", workflow_type="FIX_BUG")

    out = planner.execute(inp)
    assert isinstance(out, PlannerOutput)

    # First task should be assigned to debugger
    assert out.tasks[0].assigned_agent == "debugger"
    assert "Diagnose" in out.tasks[0].task_name


def test_planner_code_review_plan():
    planner = PlannerAgent()
    inp = PlannerInput(goal="Audit security of payment module", workflow_type="CODE_REVIEW")

    out = planner.execute(inp)
    assert isinstance(out, PlannerOutput)
    assert len(out.tasks) == 1
    assert out.tasks[0].assigned_agent == "reviewer"

