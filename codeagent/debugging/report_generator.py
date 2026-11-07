"""Debugging report generator formatting diagnostic outcomes for Rich terminal display and markdown."""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from codeagent.debugging.error_detector import DetectedError
from codeagent.debugging.fix_generator import ProposedFix
from codeagent.debugging.regression_checker import RegressionReport, RegressionStatus
from codeagent.debugging.retest_manager import RetestResult
from codeagent.debugging.root_cause_analyzer import RootCauseDiagnosis


class DebugReport(BaseModel):
    """Complete diagnostic and repair session report."""

    session_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: DetectedError
    diagnosis: RootCauseDiagnosis
    proposed_fix: Optional[ProposedFix] = None
    patch_applied: bool = False
    backups_created: List[str] = Field(default_factory=list)
    retest_result: Optional[RetestResult] = None
    regression_report: Optional[RegressionReport] = None
    final_status: str = "IN_PROGRESS"
    iterations_count: int = 1

    def to_markdown(self) -> str:
        """Format report into clean markdown document."""
        lines = [
            f"# Autonomous Debugging Report — Session {self.session_id}",
            f"**Timestamp:** {self.timestamp}  ",
            f"**Final Status:** `{self.final_status}`  ",
            f"**Iterations:** {self.iterations_count}  ",
            "",
            "## 1. Detected Failure",
            f"- **Error Type:** `{self.error.error_type}`",
            f"- **Message:** {self.error.error_message}",
            f"- **Location:** `{self.error.file_path or 'Unknown'}:{self.error.line_number or '?'}`",
            "",
            "## 2. Root Cause Diagnosis",
            f"- **Summary:** {self.diagnosis.error_summary}",
            f"- **Root Cause:** {self.diagnosis.root_cause}",
            f"- **Confidence:** `{self.diagnosis.confidence.upper()}`",
            f"- **Suggested Solution:** {self.diagnosis.suggested_solution}",
            "",
        ]

        if self.proposed_fix and self.proposed_fix.patches:
            lines.append("## 3. Proposed Fix & Unified Diff")
            lines.append(f"**Description:** {self.proposed_fix.description}")
            for patch in self.proposed_fix.patches:
                lines.append(f"### Target: `{patch.file_path}`")
                lines.append("```diff")
                lines.append(patch.diff)
                lines.append("```")
            lines.append("")

        lines.append("## 4. Verification & Retest")
        lines.append(f"- **Patch Applied:** {'Yes' if self.patch_applied else 'No'}")
        if self.backups_created:
            lines.append(f"- **Backups Created:** {', '.join(self.backups_created)}")
        if self.retest_result:
            lines.append(f"- **Retest Status:** `{self.retest_result.status}`")
            lines.append(f"- **Passed / Total:** {self.retest_result.passed} / {self.retest_result.total}")
            lines.append(f"- **Remaining Failed:** {self.retest_result.new_failed}")
        if self.regression_report:
            lines.append(f"- **Regression Status:** `{self.regression_report.status.value.upper()}`")
            lines.append(f"- **Summary:** {self.regression_report.summary}")

        return "\n".join(lines)

    def render_rich(self, console: Console) -> None:
        """Render report into Rich terminal panels and tables."""
        status_color = "green" if "FIXED" in self.final_status else ("yellow" if "PARTIAL" in self.final_status else "red")

        table = Table(title=f"Autonomous Debugging Report [{self.session_id}]", show_header=True, header_style="bold magenta")
        table.add_column("Category", style="cyan", width=22)
        table.add_column("Details", style="white")

        table.add_row("Final Status", f"[{status_color}]{self.final_status}[/{status_color}]")
        table.add_row("Error Type", f"[bold red]{self.error.error_type}[/bold red]")
        table.add_row("Error Message", self.error.error_message)
        table.add_row("Location", f"{self.error.file_path or 'Unknown'}:{self.error.line_number or '?'}")
        table.add_row("Root Cause", self.diagnosis.root_cause)
        table.add_row("Confidence", f"[{'green' if self.diagnosis.confidence == 'confirmed' else 'yellow'}]{self.diagnosis.confidence.upper()}[/]")
        table.add_row("Patch Applied", "[green]Yes[/green]" if self.patch_applied else "[yellow]No[/yellow]")

        if self.retest_result:
            retest_badge = "[green]PASSED[/green]" if self.retest_result.is_resolved else "[red]FAILED[/red]"
            table.add_row("Retest Outcome", f"{retest_badge} ({self.retest_result.passed}/{self.retest_result.total} passed)")

        if self.regression_report:
            table.add_row("Regression Status", self.regression_report.status.value.upper())

        console.print(table)

        if self.proposed_fix and self.proposed_fix.patches:
            for patch in self.proposed_fix.patches:
                if patch.diff:
                    syntax = Syntax(patch.diff, "diff", theme="monokai", line_numbers=False)
                    console.print(Panel(syntax, title=f"Applied Unified Diff: {patch.file_path}", border_style="cyan"))


class ReportGenerator:
    """Generates structured DebugReport objects."""

    @staticmethod
    def create_report(
        session_id: str,
        error: DetectedError,
        diagnosis: RootCauseDiagnosis,
        proposed_fix: Optional[ProposedFix] = None,
        patch_applied: bool = False,
        backups_created: Optional[List[str]] = None,
        retest_result: Optional[RetestResult] = None,
        regression_report: Optional[RegressionReport] = None,
        iterations_count: int = 1,
    ) -> DebugReport:
        """Instantiate and populate a complete DebugReport."""
        if regression_report and regression_report.status == RegressionStatus.FIXED_AND_VERIFIED:
            final_status = "FIXED_AND_VERIFIED"
        elif patch_applied and retest_result and retest_result.is_resolved:
            final_status = "FIXED_AND_VERIFIED"
        elif patch_applied and not retest_result:
            final_status = "FIX_APPLIED_UNVERIFIED"
        elif patch_applied and retest_result and not retest_result.is_resolved:
            final_status = "STILL_FAILING"
        else:
            final_status = "UNRESOLVED"

        return DebugReport(
            session_id=session_id,
            error=error,
            diagnosis=diagnosis,
            proposed_fix=proposed_fix,
            patch_applied=patch_applied,
            backups_created=backups_created or [],
            retest_result=retest_result,
            regression_report=regression_report,
            final_status=final_status,
            iterations_count=iterations_count,
        )

