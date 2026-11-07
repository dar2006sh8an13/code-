"""Central Execution Manager coordinating validation, approvals, processes, and audit trails."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Union
import uuid

from codeagent.config.settings import Settings, get_settings
from codeagent.execution.audit_logger import AuditEntry, AuditLogger
from codeagent.execution.command_validator import CommandValidator
from codeagent.execution.dependency_manager import DependencyManager
from codeagent.execution.output_capture import ExecutionResult, OutputCapture
from codeagent.execution.permission_manager import ExecutionPlan, PermissionManager
from codeagent.execution.process_manager import ProcessInfo, ProcessManager
from codeagent.execution.python_runner import PythonRunner
from codeagent.execution.terminal import TerminalExecutor
from codeagent.execution.test_runner import TestReport, TestRunner
from codeagent.filesystem.path_validator import PathValidator


class ExecutionManager:
    """Central manager mediating all code and command execution for CodeAgent."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        workspace_root: Optional[Union[str, Path]] = None,
        approval_callback: Optional[Callable[[ExecutionPlan], bool]] = None,
    ) -> None:
        """Initialize ExecutionManager.

        Args:
            settings: Settings configuration instance.
            workspace_root: Optional workspace root override.
            approval_callback: Approval callback for user confirmation dialogs.
        """
        self.settings = settings or get_settings()
        ws = workspace_root or self.settings.workspace_root or Path.cwd()
        self.workspace_root = Path(ws).resolve()

        # Core subsystems
        self.path_validator = PathValidator(workspace_root=self.workspace_root)
        self.command_validator = CommandValidator(
            path_validator=self.path_validator,
            workspace_only=self.settings.execution_workspace_only,
        )
        self.output_capture = OutputCapture(max_size_mb=self.settings.max_output_size_mb)
        self.permission_manager = PermissionManager(
            settings=self.settings,
            approval_callback=approval_callback,
        )
        self.process_manager = ProcessManager(
            settings=self.settings,
            output_capture=self.output_capture,
        )
        self.audit_logger = AuditLogger(
            audit_file_path=self.settings.audit_log_path,
            workspace_root=self.workspace_root,
            enabled=self.settings.execution_audit_enabled,
        )

        # Specialized runners
        self.terminal = TerminalExecutor(
            process_manager=self.process_manager,
            validator=self.command_validator,
        )
        self.python_runner = PythonRunner(
            process_manager=self.process_manager,
            path_validator=self.path_validator,
        )
        self.dependency_manager = DependencyManager(
            process_manager=self.process_manager,
            permission_manager=self.permission_manager,
            path_validator=self.path_validator,
        )
        self.test_runner = TestRunner(
            process_manager=self.process_manager,
            path_validator=self.path_validator,
        )

    def _record_audit(
        self,
        operation: str,
        executable: str,
        arguments: list[str],
        cwd: Path,
        approval_status: str,
        start_time_iso: str,
        result: Optional[ExecutionResult] = None,
        error_msg: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Helper to create and persist an audit record."""
        end_time_iso = datetime.now(timezone.utc).isoformat()
        status = "error" if error_msg else ("timeout" if (result and result.timed_out) else ("success" if (result and result.success) else "failed"))

        entry = AuditEntry(
            execution_id=uuid.uuid4().hex[:10],
            operation=operation,
            executable=executable,
            arguments=arguments,
            working_directory=str(cwd),
            approval_status=approval_status,
            start_time=start_time_iso,
            end_time=end_time_iso,
            exit_code=result.exit_code if result else None,
            timeout=result.timed_out if result else False,
            status=status,
            error_message=error_msg,
            task_id=task_id,
        )
        self.audit_logger.log(entry)

    def run_python(
        self,
        script_path: Union[str, Path],
        args: Optional[list[str]] = None,
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
        approved: bool = False,
    ) -> ExecutionResult:
        """Run a Python script file with approval check and audit logging."""
        start_iso = datetime.now(timezone.utc).isoformat()
        resolved_script = self.path_validator.validate_and_resolve(script_path, allow_nonexistent=False)
        resolved_cwd = (
            self.path_validator.validate_and_resolve(cwd, allow_nonexistent=False)
            if cwd
            else resolved_script.parent
        )

        plan = ExecutionPlan(
            operation="python",
            command=f"python {resolved_script.name} {' '.join(args or [])}",
            working_directory=str(resolved_cwd),
            details={"Script": str(resolved_script), "Args": str(args or [])},
            reason="Execute Python script in project workspace",
        )

        self.permission_manager.check_and_request_approval(plan, bypass_approval=approved)

        try:
            res = self.python_runner.run_script(
                script_path=resolved_script,
                args=args,
                cwd=resolved_cwd,
                timeout=timeout,
            )
            self._record_audit(
                operation="python",
                executable="python",
                arguments=[str(resolved_script)] + (args or []),
                cwd=resolved_cwd,
                approval_status="approved",
                start_time_iso=start_iso,
                result=res,
            )
            return res
        except Exception as exc:
            self._record_audit(
                operation="python",
                executable="python",
                arguments=[str(resolved_script)] + (args or []),
                cwd=resolved_cwd,
                approval_status="approved",
                start_time_iso=start_iso,
                error_msg=str(exc),
            )
            raise

    def execute_command(
        self,
        command_or_args: Union[str, list[str]],
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
        shell_type: str = "direct",
        approved: bool = False,
    ) -> ExecutionResult:
        """Execute a validated terminal command with approval check and audit logging."""
        start_iso = datetime.now(timezone.utc).isoformat()
        cmd_str = command_or_args if isinstance(command_or_args, str) else " ".join(command_or_args)
        resolved_cwd = self.command_validator.validate_working_directory(cwd)

        plan = ExecutionPlan(
            operation="terminal",
            command=cmd_str,
            working_directory=str(resolved_cwd),
            details={"Shell Type": shell_type},
            reason="Execute terminal command in workspace",
        )

        self.permission_manager.check_and_request_approval(plan, bypass_approval=approved)

        try:
            res = self.terminal.execute(
                command_or_args=command_or_args,
                cwd=resolved_cwd,
                timeout=timeout,
                shell_type=shell_type,
            )
            self._record_audit(
                operation="terminal",
                executable=cmd_str.split()[0] if cmd_str else "unknown",
                arguments=cmd_str.split()[1:] if cmd_str else [],
                cwd=resolved_cwd,
                approval_status="approved",
                start_time_iso=start_iso,
                result=res,
            )
            return res
        except Exception as exc:
            self._record_audit(
                operation="terminal",
                executable=cmd_str.split()[0] if cmd_str else "unknown",
                arguments=cmd_str.split()[1:] if cmd_str else [],
                cwd=resolved_cwd,
                approval_status="approved",
                start_time_iso=start_iso,
                error_msg=str(exc),
            )
            raise

    def install_dependency(
        self,
        package_name: str,
        upgrade: bool = False,
        approved: bool = False,
    ) -> ExecutionResult:
        """Install a package via pip with mandatory approval and audit."""
        start_iso = datetime.now(timezone.utc).isoformat()
        try:
            res = self.dependency_manager.install_package(
                package_name=package_name,
                upgrade=upgrade,
                approved=approved,
            )
            self._record_audit(
                operation="dependency",
                executable="pip",
                arguments=["install", package_name],
                cwd=self.workspace_root,
                approval_status="approved",
                start_time_iso=start_iso,
                result=res,
            )
            return res
        except Exception as exc:
            self._record_audit(
                operation="dependency",
                executable="pip",
                arguments=["install", package_name],
                cwd=self.workspace_root,
                approval_status="rejected" if "rejected" in str(exc).lower() else "failed",
                start_time_iso=start_iso,
                error_msg=str(exc),
            )
            raise

    def install_requirements(
        self,
        requirements_file: Union[str, Path] = "requirements.txt",
        approved: bool = False,
    ) -> ExecutionResult:
        """Install all packages in a requirements file."""
        start_iso = datetime.now(timezone.utc).isoformat()
        try:
            res = self.dependency_manager.install_requirements(
                requirements_file=requirements_file,
                approved=approved,
            )
            self._record_audit(
                operation="dependency",
                executable="pip",
                arguments=["install", "-r", str(requirements_file)],
                cwd=self.workspace_root,
                approval_status="approved",
                start_time_iso=start_iso,
                result=res,
            )
            return res
        except Exception as exc:
            self._record_audit(
                operation="dependency",
                executable="pip",
                arguments=["install", "-r", str(requirements_file)],
                cwd=self.workspace_root,
                approval_status="rejected" if "rejected" in str(exc).lower() else "failed",
                start_time_iso=start_iso,
                error_msg=str(exc),
            )
            raise

    def run_tests(
        self,
        framework: Optional[str] = None,
        test_path: Optional[str] = None,
        extra_args: Optional[list[str]] = None,
        timeout: Optional[float] = None,
    ) -> TestReport:
        """Execute project tests with pytest or unittest and record audit."""
        start_iso = datetime.now(timezone.utc).isoformat()
        report = self.test_runner.run(
            framework=framework,
            test_path=test_path,
            extra_args=extra_args,
            timeout=timeout,
        )
        self._record_audit(
            operation="test",
            executable=report.framework,
            arguments=[test_path or "."] + (extra_args or []),
            cwd=self.workspace_root,
            approval_status="auto_approved",
            start_time_iso=start_iso,
            error_msg=None if report.status in ("PASSED", "FAILED") else f"Test run status: {report.status}",
        )
        return report

    def list_processes(self) -> list[ProcessInfo]:
        """List active processes."""
        return self.process_manager.list_active_processes()

    def cancel_execution(self, process_id: int) -> bool:
        """Cancel a running process by PID."""
        return self.process_manager.cancel_process(process_id)

