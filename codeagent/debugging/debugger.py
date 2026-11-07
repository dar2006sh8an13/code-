"""Autonomous debugger controller orchestrating the 16-step diagnosis, patch, and retest loop."""

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Callable, List, Optional, Union
import uuid

from codeagent.config.settings import Settings, get_settings
from codeagent.debugging.code_inspector import CodeInspector, InspectedCodeContext
from codeagent.debugging.error_detector import DetectedError, ErrorDetector
from codeagent.debugging.fix_generator import FilePatch, FixGenerator, ProposedFix
from codeagent.debugging.patch_manager import PatchManager, PatchRecord, PatchRejectedError
from codeagent.debugging.regression_checker import RegressionChecker, RegressionReport, RegressionStatus
from codeagent.debugging.report_generator import DebugReport, ReportGenerator
from codeagent.debugging.retest_manager import RetestManager, RetestResult
from codeagent.debugging.root_cause_analyzer import RootCauseAnalyzer, RootCauseDiagnosis
from codeagent.debugging.traceback_parser import TracebackParser
from codeagent.execution.manager import ExecutionManager
from codeagent.execution.output_capture import ExecutionResult
from codeagent.execution.test_runner import TestReport
from codeagent.filesystem.backup import BackupManager
from codeagent.filesystem.path_validator import PathValidator
from codeagent.filesystem.reader import FileReader
from codeagent.llm.client import LLMClient


class AutonomousDebugger:
    """Coordinates the end-to-end 16-step autonomous debugging workflow."""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        settings: Optional[Settings] = None,
        llm_client: Optional[LLMClient] = None,
        execution_manager: Optional[ExecutionManager] = None,
        backup_manager: Optional[BackupManager] = None,
        require_patch_approval: bool = True,
    ) -> None:
        """Initialize AutonomousDebugger with all supporting subsystems."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.validator = PathValidator(workspace_root=self.workspace_root)
        self.reader = FileReader(validator=self.validator)
        self.backup_manager = backup_manager or BackupManager(workspace_root=self.workspace_root)
        self.execution_manager = execution_manager or ExecutionManager(workspace_root=self.workspace_root)

        # Debugging subsystems
        self.traceback_parser = TracebackParser(workspace_root=self.workspace_root)
        self.error_detector = ErrorDetector(workspace_root=self.workspace_root)
        self.code_inspector = CodeInspector(
            workspace_root=self.workspace_root,
            path_validator=self.validator,
            reader=self.reader,
        )
        self.root_cause_analyzer = RootCauseAnalyzer(
            llm_client=self.llm_client,
            workspace_root=self.workspace_root,
        )
        self.fix_generator = FixGenerator(
            workspace_root=self.workspace_root,
            llm_client=self.llm_client,
            path_validator=self.validator,
            reader=self.reader,
        )
        self.patch_manager = PatchManager(
            workspace_root=self.workspace_root,
            backup_manager=self.backup_manager,
            path_validator=self.validator,
            reader=self.reader,
            require_approval=require_patch_approval,
        )
        self.retest_manager = RetestManager(
            execution_manager=self.execution_manager,
            workspace_root=self.workspace_root,
        )
        self.regression_checker = RegressionChecker()

        # Limits
        self.max_iterations = self.settings.max_debug_iterations
        self.max_fix_attempts = self.settings.max_fix_attempts
        self.max_retest_attempts = self.settings.max_retest_attempts
        self.timeout_seconds = self.settings.debug_timeout_seconds

    def debug_target(
        self,
        test_path: Optional[str] = None,
        script_path: Optional[str] = None,
        initial_error: Optional[DetectedError] = None,
        approval_callback: Optional[Callable[[FilePatch], bool]] = None,
        bypass_approval: bool = False,
        custom_replacement: Optional[tuple[str, str]] = None,
    ) -> DebugReport:
        """Execute the full 16-step autonomous debugging workflow."""
        session_id = uuid.uuid4().hex[:8]
        start_time = time.time()
        iterations = 0
        fix_attempts = 0
        applied_records: List[PatchRecord] = []
        backups_created: List[str] = []

        # 1. Obtain failure evidence
        detected_error = initial_error
        if not detected_error:
            if test_path:
                test_rep = self.execution_manager.run_tests(test_path=test_path)
                detected_error = self.error_detector.detect_from_test_report(test_rep)
            elif script_path:
                run_res = self.execution_manager.run_python(script_path=script_path, approved=True)
                detected_error = self.error_detector.detect_from_execution_result(run_res)

        if not detected_error:
            # No failure detected
            return DebugReport(
                session_id=session_id,
                error=DetectedError(
                    error_type="None",
                    error_message="No error or test failure detected in target.",
                    is_fatal=False,
                ),
                diagnosis=RootCauseDiagnosis(
                    error_summary="All targets passed cleanly.",
                    exception_type="None",
                    root_cause="No failure observed.",
                    suggested_solution="No action needed.",
                    confidence="confirmed",
                ),
                final_status="FIXED_AND_VERIFIED",
                iterations_count=0,
            )

        diagnosis: Optional[RootCauseDiagnosis] = None
        proposed_fix: Optional[ProposedFix] = None
        retest_result: Optional[RetestResult] = None
        regression_report: Optional[RegressionReport] = None
        patch_applied = False
        seen_patch_diffs: set[str] = set()

        # Autonomous debug loop
        while iterations < self.max_iterations and fix_attempts < self.max_fix_attempts:
            iterations += 1

            # Check overall timeout limit
            if time.time() - start_time > self.timeout_seconds:
                break

            # 4. Inspect affected source code
            target_file = detected_error.file_path
            code_ctx: Optional[InspectedCodeContext] = None
            if target_file and (self.workspace_root / target_file).exists():
                try:
                    code_ctx = self.code_inspector.inspect_file(
                        file_path=target_file,
                        target_line=detected_error.line_number,
                    )
                except Exception:
                    pass

            # 6. Analyze root cause
            diagnosis = self.root_cause_analyzer.analyze(
                error=detected_error,
                code_context=code_ctx,
            )

            # 7. Generate proposed fix
            proposed_fix = self.fix_generator.generate_fix(
                diagnosis=diagnosis,
                context=code_ctx,
                target_file_path=target_file,
                custom_replacement=custom_replacement,
            )

            if not proposed_fix.is_valid or not proposed_fix.patches:
                # Cannot generate valid patch
                break

            # Avoid repeated identical patches
            primary_diff = proposed_fix.patches[0].diff
            if primary_diff in seen_patch_diffs:
                # Avoid patch loop
                break
            seen_patch_diffs.add(primary_diff)

            fix_attempts += 1

            # 8-11. Request approval, backup, and apply patch
            try:
                records = self.patch_manager.apply_fix(
                    proposed_fix=proposed_fix,
                    approval_callback=approval_callback,
                    bypass_approval=bypass_approval,
                )
                applied_records.extend(records)
                backups_created.extend([r.backup_id for r in records])
                patch_applied = True
            except PatchRejectedError:
                # User declined patch
                patch_applied = False
                break
            except Exception:
                # Patch application failed
                patch_applied = False
                break

            # 12-14. Retest and check regression
            retest_result = self.retest_manager.retest(
                test_path=test_path,
                script_path=script_path,
                previous_failed_count=1,
            )

            regression_report = self.regression_checker.evaluate(
                retest_result=retest_result,
                patch_applied=patch_applied,
            )

            if regression_report.status == RegressionStatus.FIXED_AND_VERIFIED:
                # Successfully fixed and verified!
                break
            elif regression_report.status == RegressionStatus.STILL_FAILING:
                # Update detected error from new retest output and retry
                new_err = self.error_detector.detect_from_text(retest_result.stderr or retest_result.stdout)
                if new_err:
                    detected_error = new_err
                else:
                    break
            else:
                break

        return ReportGenerator.create_report(
            session_id=session_id,
            error=detected_error,
            diagnosis=diagnosis or RootCauseDiagnosis(
                error_summary=detected_error.to_summary(),
                exception_type=detected_error.error_type,
                root_cause="Automated diagnosis could not be finalized.",
                suggested_solution="Inspect manually.",
            ),
            proposed_fix=proposed_fix,
            patch_applied=patch_applied,
            backups_created=backups_created,
            retest_result=retest_result,
            regression_report=regression_report,
            iterations_count=iterations,
        )

    def rollback_session(self, report: DebugReport) -> int:
        """Roll back all backups created during the debugging session."""
        count = 0
        for backup_id in reversed(report.backups_created):
            try:
                self.backup_manager.restore_backup(backup_id)
                count += 1
            except Exception:
                pass
        return count
