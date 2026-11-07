"""Unit tests for CodeInspector inspecting source code, AST symbols, and related tests."""

from pathlib import Path
import pytest

from codeagent.debugging.code_inspector import CodeInspector
from codeagent.filesystem.path_validator import WorkspaceSecurityError


class TestCodeInspector:
    """Test suite for CodeInspector."""

    def test_inspect_file_context_window(self, tmp_path: Path) -> None:
        """Inspect source code around target line and format context with line numbers."""
        src_file = tmp_path / "calculator.py"
        src_file.write_text(
            "import math\n\ndef add(a, b):\n    return a + b\n\ndef divide(a, b):\n    return a / b\n\ndef multiply(a, b):\n    return a * b\n",
            encoding="utf-8",
        )

        inspector = CodeInspector(workspace_root=tmp_path)
        ctx = inspector.inspect_file(src_file, target_line=7, window=3)

        assert ctx.target_line == 7
        assert ">    7 |     return a / b" in ctx.lines_context
        assert ctx.enclosing_function == "divide"
        assert "math" in ctx.imports

    def test_inspect_class_enclosing_symbol(self, tmp_path: Path) -> None:
        """Correctly locate enclosing class and method in AST."""
        src_file = tmp_path / "service.py"
        src_file.write_text(
            "class UserService:\n    def get_user(self, uid):\n        if uid < 0:\n            raise ValueError('Invalid UID')\n        return {'id': uid}\n",
            encoding="utf-8",
        )

        inspector = CodeInspector(workspace_root=tmp_path)
        ctx = inspector.inspect_file(src_file, target_line=4)

        assert ctx.enclosing_class == "UserService"
        assert ctx.enclosing_function == "get_user"

    def test_find_related_tests(self, tmp_path: Path) -> None:
        """Discover corresponding test files in workspace."""
        app_file = tmp_path / "orders.py"
        app_file.write_text("def create_order(): pass")

        test_file = tmp_path / "test_orders.py"
        test_file.write_text("from orders import create_order\ndef test_create(): pass")

        inspector = CodeInspector(workspace_root=tmp_path)
        related_tests = inspector.find_related_tests(app_file)

        assert len(related_tests) >= 1
        assert "test_orders.py" in related_tests[0]

    def test_traversal_outside_workspace_rejected(self, tmp_path: Path) -> None:
        """Reject inspection of files outside workspace root."""
        inspector = CodeInspector(workspace_root=tmp_path)
        with pytest.raises(WorkspaceSecurityError):
            inspector.inspect_file("..\\..\\secret.py")

