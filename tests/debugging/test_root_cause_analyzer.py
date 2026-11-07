"""Unit tests for RootCauseAnalyzer diagnosing errors with heuristics and mocked LLM."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from codeagent.debugging.code_inspector import InspectedCodeContext
from codeagent.debugging.error_detector import DetectedError
from codeagent.debugging.root_cause_analyzer import ConfidenceLevel, RootCauseAnalyzer, RootCauseDiagnosis


class TestRootCauseAnalyzer:
    """Test suite for RootCauseAnalyzer."""

    def test_heuristic_zero_division_diagnosis(self, tmp_path: Path) -> None:
        """Diagnose ZeroDivisionError using heuristic rule."""
        analyzer = RootCauseAnalyzer(workspace_root=tmp_path)
        err = DetectedError(
            error_type="ZeroDivisionError",
            error_message="division by zero",
            file_path="math_utils.py",
            line_number=12,
        )
        ctx = InspectedCodeContext(
            file_path="math_utils.py",
            target_line=12,
            lines_context="> 12 | return total / count",
        )

        diag = analyzer.analyze(err, code_context=ctx)
        assert diag.exception_type == "ZeroDivisionError"
        assert "divide by zero" in diag.root_cause.lower()
        assert diag.confidence == ConfidenceLevel.CONFIRMED.value
        assert "guard" in diag.suggested_solution.lower()
        assert len(diag.evidence) >= 1

    def test_heuristic_missing_module_diagnosis(self, tmp_path: Path) -> None:
        """Diagnose ModuleNotFoundError with dependency installation advice."""
        analyzer = RootCauseAnalyzer(workspace_root=tmp_path)
        err = DetectedError(
            error_type="ModuleNotFoundError",
            error_message="No module named 'flask'",
        )

        diag = analyzer.analyze(err)
        assert diag.exception_type == "ModuleNotFoundError"
        assert "dependency" in diag.root_cause.lower() or "module" in diag.root_cause.lower()
        assert "flask" in diag.root_cause.lower()
        assert "install" in diag.suggested_solution.lower()

    def test_heuristic_key_error_diagnosis(self, tmp_path: Path) -> None:
        """Diagnose KeyError advising dict.get() check."""
        analyzer = RootCauseAnalyzer(workspace_root=tmp_path)
        err = DetectedError(
            error_type="KeyError",
            error_message="'user_token'",
            file_path="auth.py",
            line_number=45,
        )

        diag = analyzer.analyze(err)
        assert diag.exception_type == "KeyError"
        assert "lookup failed" in diag.root_cause.lower() or "key" in diag.root_cause.lower()
        assert "dict.get" in diag.suggested_solution

    def test_mocked_llm_analysis(self, tmp_path: Path) -> None:
        """Verify structured output parsing when LLM client is used."""
        mock_client = MagicMock()
        mock_client.default_model = "qwen3:latest"
        mock_client._client = MagicMock()

        analyzer = RootCauseAnalyzer(llm_client=mock_client, workspace_root=tmp_path)
        analyzer.structured_engine.generate_structured = MagicMock(
            return_value=RootCauseDiagnosis(
                error_summary="ZeroDivisionError in calculate()",
                exception_type="ZeroDivisionError",
                root_cause="Denominator evaluated to zero due to empty list input.",
                affected_file="calc.py",
                affected_line=10,
                evidence=["Stack trace points directly to calc.py:10"],
                suggested_solution="Check len(items) > 0 before dividing.",
                confidence="confirmed",
            )
        )

        err = DetectedError(error_type="ZeroDivisionError", error_message="division by zero")
        diag = analyzer.analyze(err)

        assert diag.root_cause == "Denominator evaluated to zero due to empty list input."
        assert diag.confidence == "confirmed"
        analyzer.structured_engine.generate_structured.assert_called_once()

