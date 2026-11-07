"""Safe file reader with line-range slicing, encoding detection, and binary guards."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Union

from codeagent.filesystem.path_validator import PathValidator


class FileReaderError(Exception):
    """Base exception for file reading errors."""
    pass


class FileTooLargeError(FileReaderError):
    """Raised when file size exceeds the configured maximum."""
    pass


class BinaryFileError(FileReaderError):
    """Raised when an operation attempts to read a binary file."""
    pass


BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".obj", ".o", ".a", ".lib", ".iso", ".img", ".dmg", ".zip", ".tar",
    ".gz", ".7z", ".rar", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".ico", ".bmp", ".pdf", ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".ttf", ".otf", ".woff", ".woff2", ".eot", ".sqlite", ".db",
}


@dataclass
class ReadResult:
    """Structured result returned by FileReader."""

    path: str
    content: str
    total_lines: int
    start_line: int
    end_line: int
    size_bytes: int
    encoding: str

    def to_summary(self) -> str:
        """Format a clear preview summary of the read operation."""
        return (
            f"File: {self.path} ({self.size_bytes} bytes, {self.total_lines} lines total, "
            f"showing lines {self.start_line}-{self.end_line}, encoding: {self.encoding})"
        )


class FileReader:
    """Reads text files safely within workspace with range slicing and size limits."""

    def __init__(
        self,
        validator: Optional[PathValidator] = None,
        max_file_size_mb: int = 5,
    ) -> None:
        """Initialize FileReader.

        Args:
            validator: PathValidator instance.
            max_file_size_mb: Upper limit on readable file size in MB.
        """
        self.validator = validator or PathValidator()
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    def is_binary(self, file_path: Path) -> bool:
        """Heuristically detect if a file is binary."""
        # 1. Extension check
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            return True

        # 2. Content check for null byte in first 8KB
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
                if b"\0" in chunk:
                    return True
        except Exception:
            return True
        return False

    def detect_encoding_and_read(self, file_path: Path) -> tuple[str, str]:
        """Attempt to read file with common encodings (UTF-8, UTF-16, Latin-1).

        Returns:
            tuple[str, str]: (content, encoding_name)
        """
        for enc in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read(), enc
            except (UnicodeDecodeError, UnicodeError):
                continue

        # Fallback reading with replacement
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), "utf-8 (replace)"

    def read(
        self,
        target_path: Union[str, Path],
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> ReadResult:
        """Read a file safely and return structured content.

        Args:
            target_path: File path within the workspace.
            start_line: 1-indexed starting line (inclusive).
            end_line: 1-indexed ending line (inclusive).

        Returns:
            ReadResult: Structured result with content and metadata.

        Raises:
            FileNotFoundError: If target does not exist.
            FileTooLargeError: If file exceeds maximum size.
            BinaryFileError: If file is binary.
            FileReaderError: On unexpected read errors.
        """
        resolved_path = self.validator.validate_and_resolve(
            target_path,
            allow_nonexistent=False,
            check_sensitive=True,
        )

        if not resolved_path.is_file():
            raise FileReaderError(f"Target '{resolved_path}' is not a regular file.")

        # Check file size
        file_size = resolved_path.stat().st_size
        if file_size > self.max_file_size_bytes:
            mb = file_size / (1024 * 1024)
            limit_mb = self.max_file_size_bytes / (1024 * 1024)
            raise FileTooLargeError(
                f"File '{resolved_path.name}' ({mb:.2f} MB) exceeds maximum allowed size ({limit_mb:.1f} MB)."
            )

        # Check binary
        if self.is_binary(resolved_path):
            raise BinaryFileError(
                f"Cannot read binary file '{resolved_path.name}'. Only plain text source files are supported."
            )

        # Read text
        raw_content, encoding = self.detect_encoding_and_read(resolved_path)
        lines = raw_content.splitlines(keepends=True)
        total_lines = len(lines)

        # Handle line slicing (1-indexed)
        if start_line is not None or end_line is not None:
            s_line = max(1, start_line) if start_line is not None else 1
            e_line = min(total_lines, end_line) if end_line is not None else total_lines

            if s_line > total_lines:
                selected_content = ""
            else:
                # 0-indexed slicing
                selected_lines = lines[s_line - 1 : e_line]
                selected_content = "".join(selected_lines)
        else:
            s_line = 1
            e_line = total_lines
            selected_content = raw_content

        rel_display = self.validator.get_relative_display_path(resolved_path)
        return ReadResult(
            path=rel_display,
            content=selected_content,
            total_lines=total_lines,
            start_line=s_line,
            end_line=e_line,
            size_bytes=file_size,
            encoding=encoding,
        )

