"""Unit tests for ReportGenerator constructing markdown and Rich debugging reports."""

from io import StringIO
from rich.console import Console

from codeagent.debugging.error_detector import DetectedError
from codeagent.debugging.fix_generator import FilePatch, ProposedFix
from codeagent.debugging.regression_checker import RegressionReport, RegressionStatus
from codeagent.debugging.report_generator import DebugReport, ReportGenerator
from codeagent.debugging.retest_manager import RetestResult
from codeagent.debugging.root_cause_analyzer import RootCauseDiagnosis


class TestReportGenerator:
    """Test suite for ReportGenerator."""

    def test_create_and_format_markdown_report(self) -> None:
        """Verify DebugReport creation and markdown formatting."""
        err = DetectedError(
            error_type="ZeroDivisionError",
            error_message="division by zero",
            file_path="math_service.py",
            line_number=22,
        )
        diag = RootCauseDiagnosis(
            error_summary="ZeroDivisionError in math_service.py:22",
            exception_type="ZeroDivisionError",
            root_cause="Divisor was 0",
            suggested_solution="Add check",
            confidence="confirmed",
        )
        patch = FilePatch(
            file_path="math_service.py",
            original_content="x / y",
            modified_content="x / y if y != 0 else 0",
            diff="--- a/math_service.py\n+++ b/math_service.py\n@@ -1 +1 @@\n-x / y\n+x / y if y != 0 else 0",
            explanation="Guard division",
        )
        fix = ProposedFix(fix_id="f1", description="Div fix", patches=[patch])
        retest = RetestResult(
            test_target="tests/test_math.py",
            passed=5,
            new_failed=0,
            total=5,
            is_resolved=True,
            status="PASSED",
        )
        reg = RegressionReport(
            status=RegressionStatus.FIXED_AND_VERIFIED,
            original_error_cleared=True,
            summary="Clean pass",
        )

        report = ReportGenerator.create_report(
            session_id="sess_123",
            error=err,
            diagnosis=diag,
            proposed_fix=fix,
            patch_applied=True,
            backups_created=["backup_001"],
            retest_result=retest,
            regression_report=reg,
            iterations_count=1,
        )

        assert report.final_status == "FIXED_AND_VERIFIED"
        md_text = report.to_markdown()

        assert "# Autonomous Debugging Report — Session sess_123" in md_text
        assert "ZeroDivisionError" in md_text
        assert "backup_001" in md_text
        assert "```diff" in md_text
        assert "FIXED_AND_VERIFIED" in md_text

    def test_rich_terminal_rendering(self) -> None:
        """Verify report renders cleanly to Rich console without exceptions."""
        err = DetectedError(error_type="ValueError", error_message="Invalid argument")
        diag = RootCauseDiagnosis(
            error_summary="ValueError",
            exception_type="ValueError",
            root_cause="Type mismatch",
            suggested_solution="Cast",
        )
        report = ReportGenerator.create_report(
            session_id="sess_test",
            error=err,
            diagnosis=diag,
        )

        buf = StringIO()
        test_console = Console(file=buf, force_terminal=True, width=100)
        report.render_rich(test_console)
        output = buf.getvalue()

        assert "Autonomous Debugging Report" in output
        assert "ValueError" in output

