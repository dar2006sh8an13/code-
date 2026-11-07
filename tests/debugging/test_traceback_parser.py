"""Unit tests for Python traceback parsing across Windows paths, chained exceptions, and syntax errors."""

from pathlib import Path
import pytest

from codeagent.debugging.traceback_parser import ParsedTraceback, StackFrame, TracebackParser


class TestTracebackParser:
    """Test suite for TracebackParser."""

    def test_standard_traceback_parsing(self, tmp_path: Path) -> None:
        """Parse standard Python traceback with frames and exception."""
        parser = TracebackParser(workspace_root=tmp_path)
        tb_text = """Traceback (most recent call last):
  File "C:\\Users\\dev\\project\\app.py", line 42, in calculate_metrics
    result = value / divisor
ZeroDivisionError: division by zero
"""
        parsed = parser.parse(tb_text)
        assert parsed is not None
        assert parsed.exception_type == "ZeroDivisionError"
        assert parsed.exception_message == "division by zero"
        assert len(parsed.frames) == 1
        frame = parsed.frames[0]
        assert "app.py" in frame.file_path
        assert frame.line_number == 42
        assert frame.function_name == "calculate_metrics"
        assert frame.code_context == "result = value / divisor"

    def test_windows_paths_and_backslashes(self, tmp_path: Path) -> None:
        """Parse Windows paths with drive letters and mixed slashes."""
        app_file = tmp_path / "src" / "main.py"
        app_file.parent.mkdir(parents=True, exist_ok=True)
        app_file.write_text("print(1)")

        parser = TracebackParser(workspace_root=tmp_path)
        tb_text = f"""Traceback (most recent call last):
  File "{str(app_file)}", line 15, in process_request
    data = fetch_record(record_id)
KeyError: 'missing_id'
"""
        parsed = parser.parse(tb_text)
        assert parsed is not None
        assert parsed.exception_type == "KeyError"
        assert parsed.exception_message == "'missing_id'"
        assert parsed.frames[0].is_workspace is True
        assert parsed.primary_frame.file_path == str(app_file)

    def test_syntax_error_traceback_parsing(self, tmp_path: Path) -> None:
        """Parse SyntaxError formatting with caret markers."""
        parser = TracebackParser(workspace_root=tmp_path)
        tb_text = """  File "C:\\Users\\dev\\script.py", line 12
    def broken_func(
                   ^
SyntaxError: invalid syntax
"""
        parsed = parser.parse(tb_text)
        assert parsed is not None
        assert parsed.exception_type == "SyntaxError"
        assert "invalid syntax" in parsed.exception_message
        assert parsed.is_syntax_error is True
        assert len(parsed.frames) == 1
        assert parsed.frames[0].line_number == 12

    def test_chained_exceptions_parsing(self, tmp_path: Path) -> None:
        """Parse chained exceptions and preserve parent traceback."""
        parser = TracebackParser(workspace_root=tmp_path)
        tb_text = """Traceback (most recent call last):
  File "C:\\project\\db.py", line 10, in connect
    raise ConnectionRefusedError("Database offline")
ConnectionRefusedError: Database offline

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\\project\\server.py", line 55, in start
    raise RuntimeError("Server failed to initialize") from exc
RuntimeError: Server failed to initialize
"""
        parsed = parser.parse(tb_text)
        assert parsed is not None
        assert parsed.exception_type == "RuntimeError"
        assert parsed.exception_message == "Server failed to initialize"
        assert parsed.chained_from is not None
        assert parsed.chained_from.exception_type == "ConnectionRefusedError"
        assert parsed.chained_from.exception_message == "Database offline"

    def test_incomplete_or_raw_error_message(self, tmp_path: Path) -> None:
        """Gracefully handle incomplete traces with just an exception line."""
        parser = TracebackParser(workspace_root=tmp_path)
        raw_error = "ModuleNotFoundError: No module named 'flask'"
        parsed = parser.parse(raw_error)
        assert parsed is not None
        assert parsed.exception_type == "ModuleNotFoundError"
        assert "flask" in parsed.exception_message
        assert len(parsed.frames) == 0

    def test_primary_frame_selection_prefers_workspace(self, tmp_path: Path) -> None:
        """Ensure primary_frame selects workspace frame over deep standard library frames."""
        ws_file = tmp_path / "myapp.py"
        ws_file.write_text("x = 1")

        parser = TracebackParser(workspace_root=tmp_path)
        tb_text = f"""Traceback (most recent call last):
  File "{str(ws_file)}", line 25, in user_code
    return json.loads(payload)
  File "C:\\Python312\\lib\\json\\__init__.py", line 346, in loads
    return _default_decoder.decode(s)
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
"""
        parsed = parser.parse(tb_text)
        assert parsed is not None
        primary = parsed.primary_frame
        assert primary is not None
        assert primary.file_path == str(ws_file)
        assert primary.is_workspace is True

