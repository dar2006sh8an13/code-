"""Unit tests for DependencyManager."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from codeagent.execution.dependency_manager import (
    DependencyInstallError,
    DependencyManager,
    DependencyManagerError,
)
from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.permission_manager import ExecutionNotApprovedError, PermissionManager
from codeagent.filesystem.path_validator import PathValidator


class TestDependencyManager:
    """Test suite for pip package installations and approvals."""

    def test_environment_info(self, tmp_path: Path) -> None:
        mgr = DependencyManager()
        info = mgr.get_environment_info()
        assert "python_executable" in info
        assert "version" in info

    def test_invalid_package_name_rejected(self) -> None:
        mgr = DependencyManager()
        with pytest.raises(DependencyManagerError):
            mgr.install_package("malicious; rm -rf /")

    def test_install_without_approval_rejected(self, tmp_path: Path) -> None:
        mgr = DependencyManager(path_validator=PathValidator(workspace_root=tmp_path))
        with pytest.raises(ExecutionNotApprovedError):
            mgr.install_package("flask", approved=False)

    def test_install_with_approval_invokes_pip(self, tmp_path: Path) -> None:
        mock_proc_mgr = MagicMock()
        mock_proc_mgr.execute_sync.return_value = ExecutionResult(
            command="python -m pip install flask",
            exit_code=0,
            stdout="Successfully installed flask",
            stderr="",
            duration_seconds=1.2,
            timed_out=False,
            working_directory=str(tmp_path),
        )

        perm_mgr = PermissionManager(approval_callback=lambda p: True)
        mgr = DependencyManager(
            process_manager=mock_proc_mgr,
            permission_manager=perm_mgr,
            path_validator=PathValidator(workspace_root=tmp_path),
        )

        res = mgr.install_package("flask")
        assert res.success is True
        assert mock_proc_mgr.execute_sync.called

