"""Dependency manager installing packages via pip with mandatory human approval."""

import json
from pathlib import Path
import re
import sys
from typing import Optional, Union

from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.permission_manager import ExecutionPlan, PermissionManager
from codeagent.execution.process_manager import ProcessManager
from codeagent.filesystem.path_validator import PathValidator


class DependencyManagerError(Exception):
    """Base exception for dependency management errors."""
    pass


class DependencyInstallError(DependencyManagerError):
    """Raised when package installation fails."""
    pass


# Valid pip package specifier regex (e.g. "flask", "requests>=2.25.0", "pytest==8.0.0")
PACKAGE_SPEC_PATTERN = re.compile(r"^[A-Za-z0-9_\-\.\[\]]+([><=~!]=?[A-Za-z0-9_\-\.,]+)?$")


class DependencyManager:
    """Manages Python packages via pip with explicit human authorization."""

    def __init__(
        self,
        process_manager: Optional[ProcessManager] = None,
        permission_manager: Optional[PermissionManager] = None,
        path_validator: Optional[PathValidator] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        """Initialize DependencyManager.

        Args:
            process_manager: ProcessManager instance.
            permission_manager: PermissionManager for approval gates.
            path_validator: PathValidator instance.
            python_executable: Active Python interpreter path.
        """
        self.process_manager = process_manager or ProcessManager()
        self.permission_manager = permission_manager or PermissionManager()
        self.path_validator = path_validator or PathValidator()
        self.python_executable = python_executable or sys.executable

    def get_environment_info(self) -> dict[str, str]:
        """Inspect the active Python runtime environment."""
        is_venv = hasattr(sys, "real_prefix") or (sys.base_prefix != sys.prefix)
        return {
            "python_executable": self.python_executable,
            "prefix": sys.prefix,
            "version": sys.version.split()[0],
            "is_virtual_environment": str(is_venv),
        }

    def install_package(
        self,
        package_name: str,
        upgrade: bool = False,
        approved: bool = False,
    ) -> ExecutionResult:
        """Install an approved Python package using python -m pip.

        Args:
            package_name: Name and optional version constraint (e.g. "flask==3.0.0").
            upgrade: Whether to pass --upgrade.
            approved: If True, bypasses interactive approval callback.

        Returns:
            ExecutionResult: pip installation log and exit code.

        Raises:
            DependencyManagerError: If package name is invalid.
            ExecutionNotApprovedError: If approval is rejected.
            DependencyInstallError: If pip returns a non-zero exit code.
        """
        clean_spec = package_name.strip()
        if not clean_spec or not PACKAGE_SPEC_PATTERN.match(clean_spec):
            raise DependencyManagerError(
                f"Invalid or unsafe package specification: '{package_name}'."
            )

        cmd_args = [self.python_executable, "-m", "pip", "install", clean_spec]
        if upgrade:
            cmd_args.append("--upgrade")

        cmd_str = " ".join(cmd_args)
        env_info = self.get_environment_info()

        # Build execution plan for human authorization
        plan = ExecutionPlan(
            operation="dependency",
            command=cmd_str,
            working_directory=str(self.path_validator.workspace_root),
            details={
                "Package": clean_spec,
                "Python Interpreter": env_info["python_executable"],
                "Virtual Environment": env_info["is_virtual_environment"],
            },
            reason=f"Install dependency '{clean_spec}' into active environment",
        )

        # Check and request user approval (MANDATORY)
        self.permission_manager.check_and_request_approval(plan, bypass_approval=approved)

        res = self.process_manager.execute_sync(
            args=cmd_args,
            cwd=self.path_validator.workspace_root,
        )

        if not res.success:
            raise DependencyInstallError(
                f"Failed to install '{clean_spec}': {res.stderr or res.stdout}"
            )

        return res

    def install_requirements(
        self,
        requirements_file: Union[str, Path] = "requirements.txt",
        approved: bool = False,
    ) -> ExecutionResult:
        """Install dependencies from a requirements file.

        Args:
            requirements_file: Path to requirements.txt inside workspace.
            approved: If True, bypasses interactive approval callback.

        Returns:
            ExecutionResult: pip installation log.
        """
        resolved_req = self.path_validator.validate_and_resolve(
            requirements_file,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        cmd_args = [self.python_executable, "-m", "pip", "install", "-r", str(resolved_req)]
        cmd_str = " ".join(cmd_args)
        env_info = self.get_environment_info()

        plan = ExecutionPlan(
            operation="dependency",
            command=cmd_str,
            working_directory=str(self.path_validator.workspace_root),
            details={
                "Requirements File": str(resolved_req.relative_to(self.path_validator.workspace_root)),
                "Python Interpreter": env_info["python_executable"],
            },
            reason="Install all requirements listed in file",
        )

        self.permission_manager.check_and_request_approval(plan, bypass_approval=approved)

        res = self.process_manager.execute_sync(
            args=cmd_args,
            cwd=self.path_validator.workspace_root,
        )

        if not res.success:
            raise DependencyInstallError(
                f"Failed to install requirements from '{resolved_req.name}': {res.stderr or res.stdout}"
            )

        return res

