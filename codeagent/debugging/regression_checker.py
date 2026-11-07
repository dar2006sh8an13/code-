"""Regression checker evaluating verification status and detecting new failures."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from codeagent.debugging.retest_manager import RetestResult


class RegressionStatus(str, Enum):
    """Categorization of overall repair verification status."""

    FIXED_AND_VERIFIED = "fixed_and_verified"
    FIX_APPLIED_UNVERIFIED = "fix_applied_unverified"
    PARTIALLY_FIXED = "partially_fixed"
    STILL_FAILING = "still_failing"
    VERIFICATION_BLOCKED = "verification_blocked"


class RegressionReport(BaseModel):
    """Structured report classifying fix success and detecting regressions."""

    status: RegressionStatus
    original_error_cleared: bool
    new_failures_introduced: List[str] = Field(default_factory=list)
    passed_tests_count: int = 0
    failed_tests_count: int = 0
    summary: str = ""

    def to_summary(self) -> str:
        """Format an informative summary of regression check."""
        reg_warn = f"\nWARNING: {len(self.new_failures_introduced)} new failure(s) detected!" if self.new_failures_introduced else ""
        return (
            f"Regression Status: [{self.status.value.upper()}]\n"
            f"Original Error Cleared: {self.original_error_cleared}\n"
            f"Passing Tests:         {self.passed_tests_count}\n"
            f"Failing Tests:         {self.failed_tests_count}\n"
            f"Summary:               {self.summary}{reg_warn}"
        )


class RegressionChecker:
    """Evaluates whether patches resolved errors cleanly without collateral regressions."""

    def evaluate(
        self,
        retest_result: Optional[RetestResult],
        pre_fix_failed_tests: Optional[List[str]] = None,
        post_fix_failed_tests: Optional[List[str]] = None,
        patch_applied: bool = True,
    ) -> RegressionReport:
        """Analyze test outcomes to determine regression status."""
        if not patch_applied:
            return RegressionReport(
                status=RegressionStatus.STILL_FAILING,
                original_error_cleared=False,
                summary="No patch was applied; original error remains.",
            )

        if not retest_result:
            return RegressionReport(
                status=RegressionStatus.FIX_APPLIED_UNVERIFIED,
                original_error_cleared=False,
                summary="Patch was applied, but verification retest was not executed.",
            )

        if retest_result.status == "ERROR":
            return RegressionReport(
                status=RegressionStatus.VERIFICATION_BLOCKED,
                original_error_cleared=False,
                summary=f"Retest run was blocked or encountered an execution error: {retest_result.stderr}",
            )

        pre_failed = set(pre_fix_failed_tests or [])
        post_failed = set(post_fix_failed_tests or [])

        # Detect new failures that were not failing before
        new_failures = sorted(list(post_failed - pre_failed))

        if retest_result.is_resolved and not new_failures:
            return RegressionReport(
                status=RegressionStatus.FIXED_AND_VERIFIED,
                original_error_cleared=True,
                new_failures_introduced=[],
                passed_tests_count=retest_result.passed,
                failed_tests_count=retest_result.new_failed,
                summary="The failing test was resolved and all test suites passed cleanly with 0 regressions.",
            )

        if retest_result.new_failed < retest_result.previous_failed and retest_result.new_failed > 0:
            return RegressionReport(
                status=RegressionStatus.PARTIALLY_FIXED,
                original_error_cleared=False,
                new_failures_introduced=new_failures,
                passed_tests_count=retest_result.passed,
                failed_tests_count=retest_result.new_failed,
                summary=f"Partially fixed: failure count reduced from {retest_result.previous_failed} to {retest_result.new_failed}.",
            )

        return RegressionReport(
            status=RegressionStatus.STILL_FAILING,
            original_error_cleared=False,
            new_failures_introduced=new_failures,
            passed_tests_count=retest_result.passed,
            failed_tests_count=retest_result.new_failed,
            summary="Original error still failing after patch application.",
        )

