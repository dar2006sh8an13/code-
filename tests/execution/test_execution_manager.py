"""Unit tests for ExecutionManager integration and tool registry execution."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from codeagent.config.settings import Settings
from codeagent.execution.manager import ExecutionManager
from codeagent.filesystem.manager import FilesystemManager
from codeagent.tools.executor import ToolExecutor
from codeagent.tools.registry import get_default_registry


class TestExecutionManagerIntegration:
    """Test suite for integrated ExecutionManager operations and tool schemas."""

    def test_registry_contains_all_19_tools(self, tmp_path: Path) -> None:
        fs_mgr = FilesystemManager(workspace_root=tmp_path)
        exec_mgr = ExecutionManager(workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr, execution_manager=exec_mgr)

        tool_names = [t.name for t in registry.list_tools()]
        expected_tools = [
            # Calculator (6)
            "calculate", "add", "subtract", "multiply", "divide", "evaluate_expression",
            # Filesystem (7)
            "read_file", "create_file", "edit_file", "delete_file",
            "list_directory", "scan_project", "analyze_project",
            # Execution (6)
            "run_python", "execute_command", "install_dependency",
            "run_tests", "get_process_status", "cancel_execution",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool '{expected}' missing from registry."

    def test_run_python_tool_via_executor(self, tmp_path: Path) -> None:
        # Create a sample python script
        script = tmp_path / "calc_test.py"
        script.write_text("print('result:', 10 * 5)", encoding="utf-8")

        settings = Settings(_env_file=None, require_python_approval=False)
        fs_mgr = FilesystemManager(settings=settings, workspace_root=tmp_path)
        exec_mgr = ExecutionManager(settings=settings, workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr, execution_manager=exec_mgr)
        executor = ToolExecutor(registry=registry)

        res = executor.execute("run_python", {"script_path": "calc_test.py"})
        assert res.success is True
        assert "50" in res.result["stdout"]
        assert res.result["exit_code"] == 0

    def test_execute_command_tool_via_executor(self, tmp_path: Path) -> None:
        settings = Settings(_env_file=None, require_command_approval=False)
        fs_mgr = FilesystemManager(settings=settings, workspace_root=tmp_path)
        exec_mgr = ExecutionManager(settings=settings, workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr, execution_manager=exec_mgr)
        executor = ToolExecutor(registry=registry)

        res = executor.execute("execute_command", {"command": "echo test_output", "shell_type": "cmd"})
        assert res.success is True
        assert "test_output" in res.result["stdout"]

    def test_get_process_status_tool_via_executor(self, tmp_path: Path) -> None:
        fs_mgr = FilesystemManager(workspace_root=tmp_path)
        exec_mgr = ExecutionManager(workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr, execution_manager=exec_mgr)
        executor = ToolExecutor(registry=registry)

        res = executor.execute("get_process_status", {})
        assert res.success is True
        assert "processes" in res.result

