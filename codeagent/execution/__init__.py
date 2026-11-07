"""Execution package for CodeAgent (Phase 5: Terminal and Code Execution)."""

from codeagent.execution.audit_logger import AuditEntry, AuditLogger
from codeagent.execution.command_validator import (
    CommandInjectionError,
    CommandSecurityError,
    CommandValidationError,
    CommandValidator,
    DangerousCommandError,
    DisallowedExecutableError,
)
from codeagent.execution.dependency_manager import (
    DependencyInstallError,
    DependencyManager,
    DependencyManagerError,
)
from codeagent.execution.manager import ExecutionManager
from codeagent.execution.output_capture import ExecutionResult, OutputCapture
from codeagent.execution.permission_manager import (
    ExecutionDisabledError,
    ExecutionNotApprovedError,
    ExecutionPermissionError,
    ExecutionPlan,
    PermissionManager,
)
from codeagent.execution.process_manager import (
    ProcessInfo,
    ProcessLimitExceededError,
    ProcessManager,
)
from codeagent.execution.python_runner import (
    PythonRunner,
    PythonRunnerError,
    ScriptNotFoundError,
)
from codeagent.execution.terminal import TerminalExecutor
from codeagent.execution.test_runner import TestReport, TestRunner

__all__ = [
    "AuditEntry",
    "AuditLogger",
    "CommandInjectionError",
    "CommandSecurityError",
    "CommandValidationError",
    "CommandValidator",
    "DangerousCommandError",
    "DependencyInstallError",
    "DependencyManager",
    "DependencyManagerError",
    "DisallowedExecutableError",
    "ExecutionDisabledError",
    "ExecutionManager",
    "ExecutionNotApprovedError",
    "ExecutionPermissionError",
    "ExecutionPlan",
    "ExecutionResult",
    "OutputCapture",
    "PermissionManager",
    "ProcessInfo",
    "ProcessLimitExceededError",
    "ProcessManager",
    "PythonRunner",
    "PythonRunnerError",
    "ScriptNotFoundError",
    "TerminalExecutor",
    "TestReport",
    "TestRunner",
]

