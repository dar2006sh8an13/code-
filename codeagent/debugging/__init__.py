"""Autonomous debugging subsystem for Code AG."""

from codeagent.debugging.code_inspector import CodeInspector, InspectedCodeContext
from codeagent.debugging.debugger import AutonomousDebugger
from codeagent.debugging.error_detector import DetectedError, ErrorDetector
from codeagent.debugging.fix_generator import FilePatch, FixGenerator, ProposedFix
from codeagent.debugging.patch_manager import (
    PatchConflictError,
    PatchError,
    PatchManager,
    PatchRecord,
    PatchRejectedError,
    PatchVerificationError,
)
from codeagent.debugging.regression_checker import RegressionChecker, RegressionReport, RegressionStatus
from codeagent.debugging.report_generator import DebugReport, ReportGenerator
from codeagent.debugging.retest_manager import RetestManager, RetestResult
from codeagent.debugging.root_cause_analyzer import ConfidenceLevel, RootCauseAnalyzer, RootCauseDiagnosis
from codeagent.debugging.traceback_parser import ParsedTraceback, StackFrame, TracebackParser

__all__ = [
    "AutonomousDebugger",
    "CodeInspector",
    "ConfidenceLevel",
    "DebugReport",
    "DetectedError",
    "ErrorDetector",
    "FilePatch",
    "FixGenerator",
    "InspectedCodeContext",
    "ParsedTraceback",
    "PatchConflictError",
    "PatchError",
    "PatchManager",
    "PatchRecord",
    "PatchRejectedError",
    "PatchVerificationError",
    "ProposedFix",
    "RegressionChecker",
    "RegressionReport",
    "RegressionStatus",
    "ReportGenerator",
    "RetestManager",
    "RetestResult",
    "RootCauseAnalyzer",
    "RootCauseDiagnosis",
    "StackFrame",
    "TracebackParser",
]

