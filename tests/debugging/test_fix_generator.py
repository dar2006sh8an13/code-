"""Unit tests for FixGenerator producing minimal unified diffs and validating Python syntax."""

from pathlib import Path
import pytest

from codeagent.debugging.code_inspector import InspectedCodeContext
from codeagent.debugging.fix_generator import FixGenerator
from codeagent.debugging.root_cause_analyzer import RootCauseDiagnosis


class TestFixGenerator:
    """Test suite for FixGenerator."""

    def test_generate_custom_replacement_patch(self, tmp_path: Path) -> None:
        """Generate a valid patch with unified diff using explicit replacement."""
        test_file = tmp_path / "app.py"
        test_file.write_text("def calc(a, b):\n    return a / b\n", encoding="utf-8")

        generator = FixGenerator(workspace_root=tmp_path)
        diag = RootCauseDiagnosis(
            error_summary="ZeroDivisionError",
            exception_type="ZeroDivisionError",
            root_cause="Division by zero",
            affected_file="app.py",
            affected_line=2,
            suggested_solution="Guard division",
        )

        fix = generator.generate_fix(
            diagnosis=diag,
            target_file_path="app.py",
            custom_replacement=("return a / b", "return a / b if b != 0 else 0"),
        )

        assert fix.is_valid is True
        assert len(fix.patches) == 1
        patch = fix.patches[0]
        assert patch.file_path == "app.py"
        assert "return a / b if b != 0 else 0" in patch.modified_content
        assert "-    return a / b" in patch.diff
        assert "+    return a / b if b != 0 else 0" in patch.diff

        # Crucial check: verify original file on disk was NOT modified during generation
        assert test_file.read_text(encoding="utf-8") == "def calc(a, b):\n    return a / b\n"

    def test_reject_syntax_error_in_patch(self, tmp_path: Path) -> None:
        """Reject patch if the proposed modification produces invalid Python syntax."""
        test_file = tmp_path / "syntax_check.py"
        test_file.write_text("x = 10\n", encoding="utf-8")

        generator = FixGenerator(workspace_root=tmp_path)
        diag = RootCauseDiagnosis(
            error_summary="Error",
            exception_type="ValueError",
            root_cause="Fix needed",
            affected_file="syntax_check.py",
            suggested_solution="Fix it",
        )

        # Propose broken syntax: `x = def return (`
        fix = generator.generate_fix(
            diagnosis=diag,
            target_file_path="syntax_check.py",
            custom_replacement=("x = 10", "x = def return ("),
        )

        assert fix.is_valid is False
        assert "syntax" in fix.validation_error.lower()
        assert len(fix.patches) == 0

    def test_reject_empty_diff_patch(self, tmp_path: Path) -> None:
        """Reject patch when modified content is identical to original content."""
        test_file = tmp_path / "same.py"
        test_file.write_text("a = 1\n", encoding="utf-8")

        generator = FixGenerator(workspace_root=tmp_path)
        diag = RootCauseDiagnosis(
            error_summary="None",
            exception_type="RuntimeError",
            root_cause="None",
            affected_file="same.py",
            suggested_solution="None",
        )

        fix = generator.generate_fix(
            diagnosis=diag,
            target_file_path="same.py",
            custom_replacement=("a = 1", "a = 1"),
        )

        assert fix.is_valid is False
        assert "empty diff" in fix.validation_error.lower() or "matches" in fix.validation_error.lower()

    def test_missing_dependency_proposes_installation(self, tmp_path: Path) -> None:
        """Identify missing dependency and populate requires_dependencies without file patches."""
        generator = FixGenerator(workspace_root=tmp_path)
        diag = RootCauseDiagnosis(
            error_summary="ModuleNotFoundError: No module named 'flask'",
            exception_type="ModuleNotFoundError",
            root_cause="Flask missing",
            suggested_solution="pip install flask",
        )

        fix = generator.generate_fix(diagnosis=diag)
        assert fix.is_valid is True
        assert len(fix.patches) == 0
        assert "flask" in fix.requires_dependencies

