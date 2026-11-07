"""Unit tests for ReviewerAgent, 5-category evaluation, secret scanning, and decisions."""

from codeagent.agents.reviewer_agent import ReviewerAgent, ReviewerInput, ReviewerOutput
from codeagent.agents.workflow_state import ReviewDecision
from codeagent.config.settings import Settings
from codeagent.filesystem.manager import FilesystemManager


def test_reviewer_approved_clean_code(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    fs = FilesystemManager(settings=settings)
    reviewer = ReviewerAgent(filesystem_manager=fs, settings=settings)

    clean_file = tmp_path / "service.py"
    clean_file.write_text("def get_data():\n    return {'status': 'ok'}\n", encoding="utf-8")

    inp = ReviewerInput(
        task_id="rev_1",
        task_name="Data service",
        files_to_review=["service.py"],
        test_results={"passed": 2, "failed": 0},
    )

    out = reviewer.execute(inp)
    assert out.decision == ReviewDecision.APPROVED
    assert len(out.findings) == 0


def test_reviewer_rejects_exposed_secret(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    fs = FilesystemManager(settings=settings)
    reviewer = ReviewerAgent(filesystem_manager=fs, settings=settings)

    leaky_file = tmp_path / "config_leak.py"
    leaky_file.write_text("API_KEY = 'sk-123456789012345678901234567890'\n", encoding="utf-8")

    inp = ReviewerInput(
        task_id="rev_sec",
        task_name="Config setup",
        files_to_review=["config_leak.py"],
    )

    out = reviewer.execute(inp)
    assert out.decision == ReviewDecision.REJECTED
    assert any(f.category == "Security" for f in out.findings)
    assert out.severity in ("HIGH", "CRITICAL")


def test_reviewer_rejects_unsafe_os_system(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    fs = FilesystemManager(settings=settings)
    reviewer = ReviewerAgent(filesystem_manager=fs, settings=settings)

    unsafe_file = tmp_path / "danger.py"
    unsafe_file.write_text("import os\nos.system('dir ' + user_input)\n", encoding="utf-8")

    inp = ReviewerInput(
        task_id="rev_danger",
        task_name="Command runner",
        files_to_review=["danger.py"],
    )

    out = reviewer.execute(inp)
    assert out.decision == ReviewDecision.REJECTED
    assert any("os.system" in f.description for f in out.findings)


def test_reviewer_rejects_failing_tests(tmp_path):
    settings = Settings(WORKSPACE_ROOT=str(tmp_path))
    fs = FilesystemManager(settings=settings)
    reviewer = ReviewerAgent(filesystem_manager=fs, settings=settings)

    dummy = tmp_path / "util.py"
    dummy.write_text("def ok(): return True\n", encoding="utf-8")

    inp = ReviewerInput(
        task_id="rev_test_fail",
        task_name="Test failure",
        files_to_review=["util.py"],
        test_results={"passed": 3, "failed": 1},
    )

    out = reviewer.execute(inp)
    assert out.decision == ReviewDecision.REJECTED
    assert any(f.category == "Testing" for f in out.findings)

