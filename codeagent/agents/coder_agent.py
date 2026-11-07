"""Coder agent: writes, edits, and verifies implementation code under strict safety controls."""

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from codeagent.agents.base_agent import AgentContext, AgentRole, AgentStatus, BaseAgent
from codeagent.agents.file_locks import FileLockManager
from codeagent.config.settings import Settings, get_settings
from codeagent.execution.manager import ExecutionManager
from codeagent.filesystem.manager import FilesystemManager
from codeagent.llm.client import LLMClient
from codeagent.safety.backup_manager import SafetyBackupManager
from codeagent.safety.protected_paths import ProtectedPathsManager


class CodeInput(BaseModel):
    """Input payload instructing CodeAgent on what to build or modify."""

    task_id: str
    task_name: str
    description: str
    instructions: str = ""
    files_to_create: Dict[str, str] = Field(default_factory=dict)  # path -> content
    files_to_modify: Dict[str, str] = Field(default_factory=dict)  # path -> new_content / replacement
    run_tests_after: bool = False
    test_path: Optional[str] = None


CoderInput = CodeInput


class CodeOutput(BaseModel):
    """Structured result of code agent execution."""

    task_id: str
    success: bool
    files_created: List[str] = Field(default_factory=list)
    files_modified: List[str] = Field(default_factory=list)
    changes_summary: str
    verification_status: str = "UNTESTED"  # VERIFIED, TESTS_PASSED, SYNTAX_VALID, FAILED
    test_summary: Optional[Dict[str, Any]] = None
    notes: str = ""


CoderOutput = CodeOutput


class CodeAgent(BaseAgent):
    """Autonomous agent responsible for writing code, editing files safely, and verifying output."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        filesystem_manager: Optional[FilesystemManager] = None,
        execution_manager: Optional[ExecutionManager] = None,
        backup_manager: Optional[SafetyBackupManager] = None,
        protected_paths_manager: Optional[ProtectedPathsManager] = None,
        file_lock_manager: Optional[FileLockManager] = None,
        llm_client: Optional[LLMClient] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize CodeAgent."""
        cfg = settings or get_settings()
        target_model = cfg.coder_model or cfg.agent_model or cfg.model_name
        super().__init__(
            agent_id=agent_id or f"code_{uuid.uuid4().hex[:8]}",
            name="CodeAgent",
            role=AgentRole.CODER,
            description="Generates, modifies, and validates source code under safety guardrails",
            system_instructions=(
                "You are the Code Agent. Your job is to implement assigned coding tasks. "
                "Always adhere to clean code conventions and safety policies. "
                "Never modify protected system files. Always create backups before editing."
            ),
            capabilities=["code_generation", "file_creation", "file_editing", "test_verification", "syntax_check"],
            tools=["read_file", "create_file", "edit_file", "delete_file", "list_directory", "run_python", "run_tests", "create_backup"],
            input_schema=CodeInput,
            output_schema=CodeOutput,
            settings=cfg,
        )
        self.fs_manager = filesystem_manager or FilesystemManager(settings=cfg)
        self.exec_manager = execution_manager or ExecutionManager(settings=cfg, workspace_root=self.fs_manager.workspace_root)
        self.backup_mgr = backup_manager or SafetyBackupManager(workspace_root=self.fs_manager.workspace_root)
        self.protected_paths = protected_paths_manager or ProtectedPathsManager(workspace_root=self.fs_manager.workspace_root)
        self.file_locks = file_lock_manager or FileLockManager(workspace_root=self.fs_manager.workspace_root)
        self.llm_client = llm_client
        self.model_name = target_model

    def execute(self, input_data: Any, context: Optional[AgentContext] = None) -> CoderOutput:
        """Execute coder implementation task with file locks, protected-path checks, and backups."""
        self.status = AgentStatus.BUSY
        coder_in = self.validate_input(input_data)
        assert isinstance(coder_in, CoderInput)

        all_target_files = list(coder_in.files_to_create.keys()) + list(coder_in.files_to_modify.keys())
        created_files: List[str] = []
        modified_files: List[str] = []

        # 1. Protected Paths Boundary Check
        for f in all_target_files:
            if self.protected_paths.is_protected(f):
                self.status = AgentStatus.FAILED
                return CoderOutput(
                    task_id=coder_in.task_id,
                    success=False,
                    changes_summary=f"Security violation: Target file '{f}' is protected.",
                    verification_status="FAILED",
                    notes="File access denied by ProtectedPathsManager",
                )

        # 2. Acquire File Locks
        acquired_locks: List[str] = []
        try:
            for f in all_target_files:
                if not self.file_locks.acquire(f, agent_id=self.agent_id, timeout=5.0):
                    raise TimeoutError(f"Could not acquire file lock for '{f}'. File is locked by another agent.")
                acquired_locks.append(f)

            # 3. Create Files
            for rel_path, content in coder_in.files_to_create.items():
                # Back up if already exists
                full_path = self.fs_manager.workspace_root / rel_path
                if full_path.exists():
                    self.backup_mgr.create_backup(rel_path)
                self.fs_manager.create_file(rel_path, content=content, overwrite=True)
                created_files.append(rel_path)

            # 4. Modify Files
            for rel_path, content in coder_in.files_to_modify.items():
                self.backup_mgr.create_backup(rel_path)
                self.fs_manager.create_file(rel_path, content=content, overwrite=True)
                modified_files.append(rel_path)

            # 5. Syntax validation for Python files
            for rel_path in created_files + modified_files:
                if rel_path.endswith(".py"):
                    full_p = self.fs_manager.workspace_root / rel_path
                    try:
                        ast.parse(full_p.read_text(encoding="utf-8"))
                    except SyntaxError as syn_err:
                        self.status = AgentStatus.FAILED
                        return CoderOutput(
                            task_id=coder_in.task_id,
                            success=False,
                            files_created=created_files,
                            files_modified=modified_files,
                            changes_summary=f"Syntax error in '{rel_path}': {syn_err}",
                            verification_status="FAILED",
                            notes="Syntax validation failed.",
                        )

            # 6. Run Tests if requested
            verification = "SYNTAX_VALID"
            test_report_dict = None
            if coder_in.run_tests_after:
                test_rep = self.exec_manager.run_tests(test_path=coder_in.test_path)
                test_report_dict = {
                    "framework": test_rep.framework,
                    "passed": test_rep.passed,
                    "failed": test_rep.failed,
                    "status": test_rep.status,
                }
                verification = "TESTS_PASSED" if test_rep.failed == 0 else "FAILED"
                if test_rep.failed > 0:
                    self.status = AgentStatus.FAILED
                    return CoderOutput(
                        task_id=coder_in.task_id,
                        success=False,
                        files_created=created_files,
                        files_modified=modified_files,
                        changes_summary=f"Tests failed after modifications ({test_rep.failed} failing).",
                        verification_status="FAILED",
                        test_summary=test_report_dict,
                    )

            self.status = AgentStatus.COMPLETED
            return CoderOutput(
                task_id=coder_in.task_id,
                success=True,
                files_created=created_files,
                files_modified=modified_files,
                changes_summary=f"Successfully applied changes ({len(created_files)} created, {len(modified_files)} modified).",
                verification_status=verification,
                test_summary=test_report_dict,
                notes=coder_in.instructions or "Implemented successfully.",
            )

        finally:
            # Release all acquired locks
            for f in acquired_locks:
                self.file_locks.release(f, agent_id=self.agent_id)


# Backwards-compatible aliases
CoderAgent = CodeAgent


