"""Unit tests for RegressionChecker classifying fix status and detecting collateral test regressions."""

import pytest

from codeagent.debugging.regression_checker import RegressionChecker, RegressionStatus
from codeagent.debugging.retest_manager import RetestResult


class TestRegressionChecker:
    """Test suite for RegressionChecker."""

    def test_fixed_and_verified(self) -> None:
        """Evaluate clean fix with 0 failures and 0 regressions."""
        checker = RegressionChecker()
        retest_res = RetestResult(
            test_target="tests/test_api.py",
            previous_failed=1,
            new_failed=0,
            passed=5,
            total=5,
            is_resolved=True,
            status="PASSED",
        )

        rep = checker.evaluate(retest_result=retest_res, patch_applied=True)
        assert rep.status == RegressionStatus.FIXED_AND_VERIFIED
        assert rep.original_error_cleared is True
        assert len(rep.new_failures_introduced) == 0

    def test_partially_fixed(self) -> None:
        """Evaluate case where failure count decreased but remains > 0."""
        checker = RegressionChecker()
        retest_res = RetestResult(
            test_target="tests/test_all.py",
            previous_failed=3,
            new_failed=1,
            passed=4,
            total=5,
            is_resolved=False,
            status="FAILED",
        )

        rep = checker.evaluate(retest_result=retest_res, patch_applied=True)
        assert rep.status == RegressionStatus.PARTIALLY_FIXED
        assert rep.original_error_cleared is False

    def test_regression_detected(self) -> None:
        """Detect new failures that were not in the pre-fix failure list."""
        checker = RegressionChecker()
        retest_res = RetestResult(
            test_target="tests/test_all.py",
            previous_failed=1,
            new_failed=1,
            passed=3,
            total=4,
            is_resolved=False,
            status="FAILED",
        )

        rep = checker.evaluate(
            retest_result=retest_res,
            pre_fix_failed_tests=["test_divide_by_zero"],
            post_fix_failed_tests=["test_divide_by_zero", "test_overflow"],
            patch_applied=True,
        )
        assert "test_overflow" in rep.new_failures_introduced

    def test_fix_applied_unverified(self) -> None:
        """Classify status as unverified when patch was applied but retest is missing."""
        checker = RegressionChecker()
        rep = checker.evaluate(retest_result=None, patch_applied=True)
        assert rep.status == RegressionStatus.FIX_APPLIED_UNVERIFIED

    def test_verification_blocked(self) -> None:
        """Classify status as blocked when retest encounters execution crash."""
        checker = RegressionChecker()
        retest_res = RetestResult(
            test_target="tests/",
            previous_failed=1,
            new_failed=0,
            passed=0,
            total=0,
            is_resolved=False,
            status="ERROR",
            stderr="Virtual environment missing pytest",
        )

        rep = checker.evaluate(retest_result=retest_res, patch_applied=True)
        assert rep.status == RegressionStatus.VERIFICATION_BLOCKED

