"""Python traceback parser converting untrusted terminal error outputs into structured Pydantic models."""

from pathlib import Path
import re
from typing import List, Optional
from pydantic import BaseModel, Field


class StackFrame(BaseModel):
    """Structured representation of a single frame in a call stack."""

    file_path: str
    line_number: int
    function_name: str
    code_context: Optional[str] = None
    is_workspace: bool = False

    def to_summary(self) -> str:
        """Format frame as file:line in function."""
        return f"{self.file_path}:{self.line_number} in {self.function_name}"


class ParsedTraceback(BaseModel):
    """Structured representation of a parsed Python traceback."""

    exception_type: str
    exception_message: str
    frames: List[StackFrame] = Field(default_factory=list)
    chained_from: Optional["ParsedTraceback"] = None
    raw_text: str = ""
    is_syntax_error: bool = False

    @property
    def primary_frame(self) -> Optional[StackFrame]:
        """Return the most relevant frame (preferring workspace frame, else the deepest frame)."""
        if not self.frames:
            return None
        # Look from deepest frame backwards for workspace code
        for frame in reversed(self.frames):
            if frame.is_workspace:
                return frame
        return self.frames[-1]


class TracebackParser:
    """Parses standard, chained, multiline, and Windows Python tracebacks safely."""

    # Matches: File "C:\path\to\file.py", line 42, in my_func
    FRAME_PATTERN = re.compile(
        r'File\s+["\'](?P<path>[^"\']+)["\'],\s+line\s+(?P<line>\d+)(?:,\s+in\s+(?P<func>[^\n]+))?',
        re.MULTILINE,
    )

    # Matches standard exception line: ValueError: invalid literal
    EXCEPTION_PATTERN = re.compile(
        r"^(?P<type>[a-zA-Z_][a-zA-Z0-9_\.]*(?:Error|Exception|Warning|Interrupt|Exit)):\s*(?P<msg>.*)$",
        re.MULTILINE,
    )

    # Matches SyntaxError / IndentationError line format
    SYNTAX_ERROR_PATTERN = re.compile(
        r"^(?P<type>SyntaxError|IndentationError|TabError):\s*(?P<msg>.*)$",
        re.MULTILINE,
    )

    CHAIN_PATTERN = re.compile(
        r"(?:The above exception was the direct cause of the following exception:|During handling of the above exception, another exception occurred:)",
        re.MULTILINE,
    )

    PYTEST_FRAME_PATTERN = re.compile(
        r"^(?P<path>[a-zA-Z0-9_\-\.\/\\]+\.py):(?P<line>\d+):(?:\s*(?P<exc>[a-zA-Z0-9_]+))?",
        re.MULTILINE,
    )

    PYTEST_ERROR_PATTERN = re.compile(
        r"^E\s+(?P<type>[a-zA-Z_][a-zA-Z0-9_\.]*(?:Error|Exception)):\s*(?P<msg>.*)$",
        re.MULTILINE,
    )

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        """Initialize parser with optional workspace root for frame localization."""
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def _is_workspace_path(self, file_path_str: str) -> bool:
        """Check if file path lies within workspace."""
        try:
            p = Path(file_path_str)
            if not p.is_absolute():
                p = (self.workspace_root / p).resolve()
            else:
                p = p.resolve()
            p.relative_to(self.workspace_root)
            return True
        except (ValueError, Exception):
            return False

    def parse(self, text: str) -> Optional[ParsedTraceback]:
        """Parse raw error output into structured ParsedTraceback.

        Handles chained exceptions recursively.
        """
        if not text or not text.strip():
            return None

        # Check for chained exception sections
        chain_matches = list(self.CHAIN_PATTERN.finditer(text))
        if chain_matches:
            # Split into parent and child traceback parts
            first_chain = chain_matches[0]
            parent_text = text[:first_chain.start()].strip()
            child_text = text[first_chain.end():].strip()

            parent_parsed = self._parse_single_traceback(parent_text)
            child_parsed = self._parse_single_traceback(child_text)

            if child_parsed and parent_parsed:
                child_parsed.chained_from = parent_parsed
                return child_parsed
            return child_parsed or parent_parsed

        return self._parse_single_traceback(text)

    def _parse_single_traceback(self, text: str) -> Optional[ParsedTraceback]:
        """Parse a single traceback block without chaining."""
        frames: List[StackFrame] = []
        is_syntax = False

        # Extract frames
        matches = list(self.FRAME_PATTERN.finditer(text))
        for i, match in enumerate(matches):
            f_path = match.group("path").strip()
            line_no = int(match.group("line"))
            func = (match.group("func") or "<module>").strip()

            # Find context line following the File line if available
            start_pos = match.end()
            next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            context_block = text[start_pos:next_start].strip().split("\n")
            code_line = context_block[0].strip() if context_block else None

            frames.append(
                StackFrame(
                    file_path=f_path,
                    line_number=line_no,
                    function_name=func,
                    code_context=code_line if code_line and not code_line.startswith("Traceback") else None,
                    is_workspace=self._is_workspace_path(f_path),
                )
            )

        # Check for pytest-style frames if standard frames not found
        if not frames:
            pytest_matches = list(self.PYTEST_FRAME_PATTERN.finditer(text))
            for p_match in pytest_matches:
                f_path = p_match.group("path").strip()
                line_no = int(p_match.group("line"))
                frames.append(
                    StackFrame(
                        file_path=f_path,
                        line_number=line_no,
                        function_name="<module>",
                        code_context=None,
                        is_workspace=self._is_workspace_path(f_path),
                    )
                )

        # Detect syntax error
        syntax_match = self.SYNTAX_ERROR_PATTERN.search(text)
        pytest_err = self.PYTEST_ERROR_PATTERN.search(text)
        if syntax_match:
            exc_type = syntax_match.group("type")
            exc_msg = syntax_match.group("msg").strip()
            is_syntax = True
        elif pytest_err:
            exc_type = pytest_err.group("type")
            exc_msg = pytest_err.group("msg").strip()
        else:
            # Find regular exception
            exc_matches = list(self.EXCEPTION_PATTERN.finditer(text))
            if exc_matches:
                # Use the last exception match in the section
                last_exc = exc_matches[-1]
                exc_type = last_exc.group("type")
                exc_msg = last_exc.group("msg").strip()
            else:
                # Incomplete or non-standard traceback: fallback extraction
                lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
                if not lines:
                    return None
                last_line = lines[-1]
                # Look for an embedded ExceptionName: message in the line
                exc_inline = self.EXCEPTION_PATTERN.search(last_line)
                if exc_inline:
                    exc_type = exc_inline.group("type")
                    exc_msg = exc_inline.group("msg").strip()
                elif ":" in last_line and " " not in last_line.split(":", 1)[0]:
                    parts = last_line.split(":", 1)
                    exc_type = parts[0].strip()
                    exc_msg = parts[1].strip()
                else:
                    exc_type = "RuntimeError"
                    exc_msg = last_line

        if not frames and exc_type == "RuntimeError" and not exc_msg:
            return None

        return ParsedTraceback(
            exception_type=exc_type,
            exception_message=exc_msg,
            frames=frames,
            raw_text=text.strip(),
            is_syntax_error=is_syntax,
        )
