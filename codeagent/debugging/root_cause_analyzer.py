"""Root cause analyzer synthesizing error tracebacks and code context using Qwen3 and heuristics."""

from enum import Enum
import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from codeagent.debugging.code_inspector import InspectedCodeContext
from codeagent.debugging.error_detector import DetectedError
from codeagent.llm.client import LLMClient
from codeagent.llm.structured import StructuredResponseEngine


class ConfidenceLevel(str, Enum):
    """Confidence classification for diagnostic conclusions."""

    CONFIRMED = "confirmed"
    LIKELY = "likely"
    HYPOTHESIS = "hypothesis"


class RootCauseDiagnosis(BaseModel):
    """Structured diagnostic report identifying error root cause and evidence."""

    error_summary: str
    exception_type: str
    root_cause: str
    affected_file: Optional[str] = None
    affected_line: Optional[int] = None
    related_code: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)
    suggested_solution: str
    confidence: str = ConfidenceLevel.LIKELY.value
    remaining_uncertainty: Optional[str] = None

    def to_summary(self) -> str:
        """Format an informative summary of diagnosis."""
        loc = f" in {self.affected_file}:{self.affected_line}" if self.affected_file else ""
        return (
            f"Diagnosis [{self.confidence.upper()}]{loc}\n"
            f"Exception:  {self.exception_type}\n"
            f"Root Cause: {self.root_cause}\n"
            f"Solution:   {self.suggested_solution}"
        )


class RootCauseAnalyzer:
    """Diagnoses root causes from error details and source inspection using Qwen3 with offline heuristics."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        workspace_root: Optional[Path] = None,
    ) -> None:
        """Initialize RootCauseAnalyzer."""
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.llm_client = llm_client
        self.structured_engine = StructuredResponseEngine()

    def analyze(
        self,
        error: DetectedError,
        code_context: Optional[InspectedCodeContext] = None,
    ) -> RootCauseDiagnosis:
        """Analyze root cause using LLM if available, falling back to deterministic heuristic diagnosis."""
        # Try LLM structured analysis if client configured
        if self.llm_client:
            try:
                diag = self._analyze_with_llm(error, code_context)
                if diag:
                    return diag
            except Exception:
                # Fall back to heuristic rule-based diagnosis on connection/timeout error
                pass

        return self._heuristic_analyze(error, code_context)

    def _analyze_with_llm(
        self,
        error: DetectedError,
        context: Optional[InspectedCodeContext],
    ) -> Optional[RootCauseDiagnosis]:
        """Perform structured LLM root cause analysis using Qwen3."""
        ctx_snippet = context.lines_context if context else "No source code available."
        prompt = (
            f"Analyze this Python error and provide a precise root cause diagnosis.\n\n"
            f"Error Type: {error.error_type}\n"
            f"Error Message: {error.error_message}\n"
            f"Target Location: {error.file_path}:{error.line_number}\n"
            f"Raw Traceback:\n{error.raw_traceback or 'None'}\n\n"
            f"Source Code Context:\n{ctx_snippet}\n\n"
            f"Distinguish strictly between confirmed root cause (direct evidence), "
            f"likely root cause, and unverified hypothesis. Do not hallucinate files or lines."
        )

        try:
            return self.structured_engine.generate_structured(
                client=self.llm_client._client,
                prompt=prompt,
                schema_class=RootCauseDiagnosis,
                model=self.llm_client.default_model,
            )
        except Exception:
            return None

    def _heuristic_analyze(
        self,
        error: DetectedError,
        context: Optional[InspectedCodeContext],
    ) -> RootCauseDiagnosis:
        """Deterministic heuristic diagnosis engine for offline and rule-based reliability."""
        err_type = error.error_type
        err_msg = error.error_message
        target_file = error.file_path
        target_line = error.line_number
        evidence = [f"Detected {err_type}: '{err_msg}'"]
        uncertainty = None
        confidence = ConfidenceLevel.CONFIRMED.value

        if context and context.lines_context:
            evidence.append(f"Inspected {context.file_path} around line {context.target_line or 'top'}")

        # Rule-based classifications
        if err_type in ("ModuleNotFoundError", "ImportError"):
            root_cause = f"The required dependency or module is not installed in the active environment: {err_msg}"
            solution = f"Install the missing dependency using dependency manager or verify the import path."
        elif err_type == "ZeroDivisionError":
            root_cause = f"An arithmetic division operation attempted to divide by zero: {err_msg}"
            solution = "Add a guard condition to check that the divisor is non-zero before dividing."
        elif err_type == "TypeError":
            root_cause = f"An operation or function was applied to an object of inappropriate type: {err_msg}"
            solution = "Cast argument to expected type or validate operand types prior to execution."
            confidence = ConfidenceLevel.LIKELY.value
        elif err_type == "KeyError":
            root_cause = f"Dictionary key lookup failed for non-existent key: {err_msg}"
            solution = "Use dict.get(key, default) or verify that the key exists before indexing."
        elif err_type == "IndexError":
            root_cause = f"Sequence index out of range: {err_msg}"
            solution = "Ensure index is within bounds of sequence length (len(seq) > index)."
        elif err_type in ("SyntaxError", "IndentationError"):
            root_cause = f"Invalid Python syntax or indentation structure: {err_msg}"
            solution = "Correct the syntax error or fix indentation spacing on the indicated line."
        elif err_type == "NameError":
            root_cause = f"Local or global name is referenced before declaration: {err_msg}"
            solution = "Define the variable before reference or check for typo in identifier name."
        elif err_type == "FileNotFoundError":
            root_cause = f"File system path does not exist on disk: {err_msg}"
            solution = "Verify the target path exists, or create parent directories and file if missing."
        elif err_type == "AssertionError":
            root_cause = f"A test assertion failed or condition evaluated to false: {err_msg}"
            solution = "Inspect the actual output vs expected output and correct the underlying logic."
            confidence = ConfidenceLevel.LIKELY.value
        else:
            root_cause = f"Runtime exception occurred during execution: {err_msg}"
            solution = "Inspect call stack and add defensive validation around the failing operation."
            confidence = ConfidenceLevel.HYPOTHESIS.value
            uncertainty = "Exact root cause depends on runtime state."

        return RootCauseDiagnosis(
            error_summary=f"{err_type}: {err_msg}",
            exception_type=err_type,
            root_cause=root_cause,
            affected_file=target_file,
            affected_line=target_line,
            related_code=context.lines_context if context else None,
            evidence=evidence,
            suggested_solution=solution,
            confidence=confidence,
            remaining_uncertainty=uncertainty,
        )

