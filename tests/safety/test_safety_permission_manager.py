"""Unit tests for centralized command permission manager evaluating ALLOW, REQUIRE_APPROVAL, and DENY."""

from pathlib import Path
import pytest

from codeagent.safety.permission_manager import PolicyVerdict, SafetyPermissionManager


@pytest.fixture
def perm_mgr() -> SafetyPermissionManager:
    return SafetyPermissionManager()


def test_readonly_commands_allowed(perm_mgr: SafetyPermissionManager) -> None:
    """Verify that read-only queries receive ALLOW verdict."""
    for cmd in ["git status", "git diff", "git log -n 5", "git branch --list", "pytest", "python --version"]:
        res = perm_mgr.evaluate_command(cmd)
        assert res.verdict == PolicyVerdict.ALLOW
        assert res.requires_approval is False


def test_mutating_commands_require_approval(perm_mgr: SafetyPermissionManager) -> None:
    """Verify that state-mutating commands receive REQUIRE_APPROVAL verdict."""
    for cmd in [
        "git add src/app.py",
        "git commit -m 'fix: bug'",
        "git switch feature/login",
        "pip install fastapi",
        "python scripts/migrate.py",
    ]:
        res = perm_mgr.evaluate_command(cmd)
        assert res.verdict == PolicyVerdict.REQUIRE_APPROVAL
        assert res.requires_approval is True


def test_destructive_commands_denied(perm_mgr: SafetyPermissionManager) -> None:
    """Verify that dangerous and destructive commands receive DENY verdict."""
    denied_commands = [
        "git push origin main --force",
        "git push origin +main:main",
        "git push -f",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "rm -rf /",
        "del /s /q C:\\",
        "format D:",
        "shutdown /s /t 0",
        "sudo rm -rf",
    ]
    for cmd in denied_commands:
        res = perm_mgr.evaluate_command(cmd)
        assert res.verdict == PolicyVerdict.DENY
        assert res.requires_approval is False


def test_shell_injection_and_chaining_denied(perm_mgr: SafetyPermissionManager) -> None:
    """Verify that chaining operators (; & | ` $()) are immediately blocked."""
    injections = [
        "git status; rm -rf .",
        "git status && git push --force",
        "dir | powershell -Command Get-Process",
        "echo `whoami`",
        "python $(whoami).py",
    ]
    for cmd in injections:
        res = perm_mgr.evaluate_command(cmd)
        assert res.verdict == PolicyVerdict.DENY
        assert "chaining" in res.reason.lower()

