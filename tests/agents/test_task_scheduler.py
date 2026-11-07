"""Unit tests for TaskScheduler, DAG ordering, cycle detection, and cascading failure blocks."""

import pytest
from codeagent.agents.base_agent import AgentRole
from codeagent.agents.task_scheduler import (
    DependencyCycleError,
    TaskScheduler,
    TaskStatus,
    WorkflowTask,
)


def test_task_scheduler_priority_and_ready_resolution():
    sched = TaskScheduler(workflow_id="wf_test")

    # t1 (no deps, priority 5)
    t1 = WorkflowTask(task_id="t1", workflow_id="wf_test", name="T1", priority=5)
    # t2 (no deps, priority 9)
    t2 = WorkflowTask(task_id="t2", workflow_id="wf_test", name="T2", priority=9)
    # t3 (depends on t1, priority 8)
    t3 = WorkflowTask(task_id="t3", workflow_id="wf_test", name="T3", dependencies=["t1"], priority=8)

    sched.add_task(t1)
    sched.add_task(t2)
    sched.add_task(t3)

    # Initial ready tasks should be t2 then t1 (ordered by priority descending)
    ready = sched.get_ready_tasks()
    assert len(ready) == 2
    assert ready[0].task_id == "t2"
    assert ready[1].task_id == "t1"

    # Complete t1
    sched.mark_completed("t1")

    # Now t3 should be ready
    ready2 = sched.get_ready_tasks()
    assert any(t.task_id == "t3" for t in ready2)


def test_task_scheduler_cycle_detection():
    sched = TaskScheduler(workflow_id="wf_cycle")

    t1 = WorkflowTask(task_id="a", workflow_id="wf_cycle", name="A", dependencies=["c"])
    t2 = WorkflowTask(task_id="b", workflow_id="wf_cycle", name="B", dependencies=["a"])
    t3 = WorkflowTask(task_id="c", workflow_id="wf_cycle", name="C", dependencies=["b"])

    sched.add_task(t1)
    sched.add_task(t2)

    with pytest.raises(DependencyCycleError) as exc_info:
        sched.add_task(t3)

    assert "Circular dependency detected" in str(exc_info.value)


def test_task_scheduler_cascade_blocked_on_failure():
    sched = TaskScheduler(workflow_id="wf_fail")

    t1 = WorkflowTask(task_id="t1", workflow_id="wf_fail", name="Root")
    t2 = WorkflowTask(task_id="t2", workflow_id="wf_fail", name="Child", dependencies=["t1"])
    t3 = WorkflowTask(task_id="t3", workflow_id="wf_fail", name="Grandchild", dependencies=["t2"])

    sched.add_task(t1)
    sched.add_task(t2)
    sched.add_task(t3)

    sched.mark_failed("t1", error="Root crash")

    assert sched.get_task("t1").status == TaskStatus.FAILED
    assert sched.get_task("t2").status == TaskStatus.BLOCKED
    assert sched.get_task("t3").status == TaskStatus.BLOCKED
    assert sched.has_failed_tasks() is True
    assert sched.is_workflow_complete() is True

