"""Unit tests for DebuggerAgent, root cause confidence levels, and loop limits."""

from codeagent.agents.debugger_agent import (
    DebuggerAgent,
    DebuggerInput,
    DebuggerOutput,
    RootCauseConfidence,
)
from codeagent.config.settings import Settings


def test_debugger_traceback_analysis_confirmed_level(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    agent = DebuggerAgent(settings=settings)

    sample_traceback = """
Traceback (most recent call last):
  File "app/main.py", line 42, in calculate_ratio
    result = total / count
ZeroDivisionError: division by zero
"""
    inp = DebuggerInput(
        task_id="dbg_1",
        error_text=sample_traceback,
        target_file="app/main.py",
        target_line=42,
    )

    out = agent.execute(inp)
    assert isinstance(out, DebuggerOutput)
    assert out.root_cause_type == "ZeroDivisionError"
    assert out.confidence_level in (RootCauseConfidence.CONFIRMED, RootCauseConfidence.LIKELY)
    assert "ZeroDivisionError" in out.summary


def test_debugger_generic_error_unverified_hypothesis(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    agent = DebuggerAgent(settings=settings)

    vague_error = "Something failed in the execution pipeline without a traceback."
    inp = DebuggerInput(task_id="dbg_2", error_text=vague_error)

    out = agent.execute(inp)
    assert out.confidence_level == RootCauseConfidence.UNVERIFIED_HYPOTHESIS

