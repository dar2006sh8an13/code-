"""Unit tests for PermissionManager approval rules and callbacks."""

import pytest

from codeagent.config.settings import Settings
from codeagent.execution.permission_manager import (
    ExecutionDisabledError,
    ExecutionNotApprovedError,
    ExecutionPlan,
    PermissionManager,
)


class TestPermissionManager:
    """Test suite for execution permissions and authorization prompts."""

    def test_dependency_always_requires_approval(self) -> None:
        settings = Settings(_env_file=None, require_dependency_approval=True)
        pm = PermissionManager(settings=settings)

        plan = ExecutionPlan(
            operation="dependency",
            command="pip install flask",
            working_directory="/workspace",
        )

        with pytest.raises(ExecutionNotApprovedError):
            pm.check_and_request_approval(plan)

    def test_approval_callback_approved(self) -> None:
        settings = Settings(_env_file=None)
        pm = PermissionManager(settings=settings, approval_callback=lambda p: True)

        plan = ExecutionPlan(
            operation="python",
            command="python main.py",
            working_directory="/workspace",
        )

        assert pm.check_and_request_approval(plan) is True

    def test_approval_callback_rejected(self) -> None:
        settings = Settings(_env_file=None)
        pm = PermissionManager(settings=settings, approval_callback=lambda p: False)

        plan = ExecutionPlan(
            operation="terminal",
            command="echo test",
            working_directory="/workspace",
        )

        with pytest.raises(ExecutionNotApprovedError):
            pm.check_and_request_approval(plan)

    def test_execution_disabled_raises_error(self) -> None:
        settings = Settings(_env_file=None, execution_enabled=False)
        pm = PermissionManager(settings=settings)

        plan = ExecutionPlan(
            operation="python",
            command="python main.py",
            working_directory="/workspace",
        )

        with pytest.raises(ExecutionDisabledError):
            pm.check_and_request_approval(plan)

