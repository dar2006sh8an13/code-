"""Debugger agent: diagnoses errors, pinpoints root causes, and generates verified fixes."""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from codeagent.agents.base_agent import AgentContext, AgentRole, AgentStatus, BaseAgent
from codeagent.config.settings import Settings, get_settings
from codeagent.debugging.debugger import AutonomousDebugger
from codeagent.debugging.error_detector import ErrorDetector
from codeagent.debugging.traceback_parser import TracebackParser
from codeagent.execution.manager import ExecutionManager
from codeagent.filesystem.manager import FilesystemManager
from codeagent.llm.client import LLMClient


class RootCauseConfidence(str, Enum):
    """Categorized confidence levels for diagnosed root causes."""

    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNVERIFIED_HYPOTHESIS = "UNVERIFIED_HYPOTHESIS"


class DebuggerInput(BaseModel):
    """Input payload providing error details and optional test scope."""

    task_id: str
    error_text: str
    target_file: Optional[str] = None
    target_line: Optional[int] = None
    test_path: Optional[str] = None
    max_iterations: int = 3


class DebuggerOutput(BaseModel):
    """Structured report returned after autonomous debugging."""

    task_id: str
    success: bool
    root_cause_type: str = "Unknown"
    confidence_level: RootCauseConfidence = RootCauseConfidence.LIKELY
    diagnosis: str = ""
    applied_patches: List[str] = Field(default_factory=list)
    iterations_used: int = 1
    summary: str = ""
    test_results: Optional[Dict[str, Any]] = None


class DebuggerAgent(BaseAgent):
    """Autonomous debugging specialist diagnosing tracebacks, determining root causes, and repairing faults."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        debugger: Optional[AutonomousDebugger] = None,
        filesystem_manager: Optional[FilesystemManager] = None,
        execution_manager: Optional[ExecutionManager] = None,
        llm_client: Optional[LLMClient] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize DebuggerAgent."""
        cfg = settings or get_settings()
        target_model = cfg.debugger_model or cfg.agent_model or cfg.model_name
        super().__init__(
            agent_id=agent_id or f"debugger_{uuid.uuid4().hex[:8]}",
            name="DebuggerAgent",
            role=AgentRole.DEBUGGER,
            description="Analyzes errors, extracts stack frames, determines root causes, and coordinates patches",
            system_instructions=(
                "You are the Debugger Agent. Your job is to locate root causes of runtime exceptions and failed tests. "
                "Distinguish between CONFIRMED, LIKELY, and UNVERIFIED root causes. "
                "Never weaken or delete tests to mask errors."
            ),
            capabilities=["error_diagnosis", "stack_trace_analysis", "root_cause_determination", "minimal_patching", "retesting"],
            tools=["diagnose_error", "retest_code", "read_file", "run_tests", "create_backup"],
            input_schema=DebuggerInput,
            output_schema=DebuggerOutput,
            settings=cfg,
        )
        self.fs_manager = filesystem_manager or FilesystemManager(settings=cfg)
        self.exec_manager = execution_manager or ExecutionManager(settings=cfg, workspace_root=self.fs_manager.workspace_root)
        self.llm_client = llm_client
        self.debugger = debugger or AutonomousDebugger(
            workspace_root=self.fs_manager.workspace_root,
            settings=cfg,
            llm_client=llm_client,
            execution_manager=self.exec_manager,
            backup_manager=self.fs_manager.backup_manager,
        )
        self.detector = ErrorDetector(workspace_root=self.fs_manager.workspace_root)
        self.parser = TracebackParser(workspace_root=self.fs_manager.workspace_root)

    def execute(self, input_data: Any, context: Optional[AgentContext] = None) -> DebuggerOutput:
        """Execute autonomous error diagnosis and repair."""
        self.status = AgentStatus.BUSY
        debug_in = self.validate_input(input_data)
        assert isinstance(debug_in, DebuggerInput)

        # 1. Detect and parse error
        detected = self.detector.detect_from_text(debug_in.error_text)
        error_type = detected.error_type if detected else "RuntimeError"

        parsed_tb = self.parser.parse(debug_in.error_text)
        confidence = RootCauseConfidence.LIKELY
        if parsed_tb and parsed_tb.frames and parsed_tb.primary_frame:
            confidence = RootCauseConfidence.CONFIRMED
        elif not parsed_tb or not parsed_tb.frames:
            confidence = RootCauseConfidence.UNVERIFIED_HYPOTHESIS

        # 2. Run debugging session if test_path is provided
        success = False
        applied: List[str] = []
        test_res: Optional[Dict[str, Any]] = None
        diagnosis_str = f"Detected {error_type} in {debug_in.target_file or 'workspace code'}"

        if debug_in.test_path:
            try:
                report = self.debugger.debug_session(
                    test_path=debug_in.test_path,
                    max_iterations=min(debug_in.max_iterations, self.settings.max_debug_attempts),
                )
                success = report.resolved
                applied = report.applied_patches
                diagnosis_str = report.summary
                test_res = {
                    "initial_status": report.initial_test_status,
                    "final_status": report.final_test_status,
                    "iterations": len(report.iterations),
                }
            except Exception as exc:
                success = False
                diagnosis_str = f"Debugging loop failed: {exc}"
        else:
            # Static diagnosis
            success = True
            msg_str = detected.error_message if detected else debug_in.error_text[:100]
            diagnosis_str = f"Diagnosed {error_type}: {msg_str}"

        self.status = AgentStatus.COMPLETED if success else AgentStatus.FAILED
        return DebuggerOutput(
            task_id=debug_in.task_id,
            success=success,
            root_cause_type=error_type,
            confidence_level=confidence,
            diagnosis=diagnosis_str,
            applied_patches=applied,
            iterations_used=1,
            summary=diagnosis_str,
            test_results=test_res,
        )
