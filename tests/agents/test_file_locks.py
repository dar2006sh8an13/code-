"""Unit tests for FileLockManager concurrency protection and timeout handling."""

import time
from codeagent.agents.file_locks import FileLockManager


def test_file_lock_acquisition_and_release(tmp_path):
    mgr = FileLockManager(workspace_root=tmp_path)
    file_rel = "src/main.py"

    assert mgr.is_locked(file_rel) is False

    # Agent A acquires
    assert mgr.acquire(file_rel, agent_id="agent_a") is True
    assert mgr.is_locked(file_rel) is True
    assert mgr.get_owner(file_rel) == "agent_a"

    # Agent B fails to acquire (timeout 0.1s)
    assert mgr.acquire(file_rel, agent_id="agent_b", timeout=0.1) is False

    # Agent A releases
    assert mgr.release(file_rel, agent_id="agent_a") is True
    assert mgr.is_locked(file_rel) is False

    # Now Agent B can acquire
    assert mgr.acquire(file_rel, agent_id="agent_b", timeout=0.5) is True
    assert mgr.get_owner(file_rel) == "agent_b"


def test_file_lock_release_by_wrong_agent(tmp_path):
    mgr = FileLockManager(workspace_root=tmp_path)
    file_rel = "app.py"

    mgr.acquire(file_rel, agent_id="owner_agent")
    # Imposter cannot release
    assert mgr.release(file_rel, agent_id="imposter") is False
    assert mgr.is_locked(file_rel) is True


def test_file_lock_release_all(tmp_path):
    mgr = FileLockManager(workspace_root=tmp_path)
    f1 = "module_a.py"
    f2 = "module_b.py"

    mgr.acquire(f1, agent_id="coder_1")
    mgr.acquire(f2, agent_id="coder_1")
    assert mgr.is_locked(f1) is True
    assert mgr.is_locked(f2) is True

    mgr.release_all("coder_1")
    assert mgr.is_locked(f1) is False
    assert mgr.is_locked(f2) is False

