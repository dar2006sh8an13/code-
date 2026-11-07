"""Code chunker splitting source files into boundary-preserving semantic chunks."""

import hashlib
from typing import List, Optional
from pydantic import BaseModel, Field

from codeagent.indexing.symbol_extractor import ExtractedSymbol


class CodeChunk(BaseModel):
    """Structured segment of a source file preserving structural boundaries."""

    file_path: str
    chunk_index: int
    line_start: int
    line_end: int
    content: str
    content_hash: str = Field(default_factory=str)

    def model_post_init(self, __context: object) -> None:
        """Compute content hash if not provided."""
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class CodeChunker:
    """Splits source files into bounded chunks respecting classes and functions."""

    def __init__(
        self,
        target_chunk_size: int = 1200,
        overlap_chars: int = 150,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> None:
        """Initialize chunker with size and overlap preferences."""
        eff_size = chunk_size if chunk_size is not None else target_chunk_size
        eff_overlap = overlap if overlap is not None else overlap_chars
        self.target_chunk_size = max(eff_size, 100)
        self.overlap_chars = max(eff_overlap, 0)

    def chunk_text(self, content: str, file_path: str = "") -> List[CodeChunk]:
        """Convenience method chunking raw text."""
        return self.chunk_file(file_path=file_path, content=content)

    def chunk_file(
        self,
        file_path: str,
        content: str,
        symbols: Optional[List[ExtractedSymbol]] = None,
    ) -> List[CodeChunk]:
        """Split file content into structured CodeChunks."""
        if not content.strip():
            return []

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        if total_lines == 0:
            return []

        # If file is smaller than chunk size, return single chunk
        if len(content) <= self.target_chunk_size:
            chunk = CodeChunk(
                file_path=file_path,
                chunk_index=0,
                line_start=1,
                line_end=total_lines,
                content=content,
            )
            return [chunk]

        # Use symbol boundaries if available
        boundary_lines: set[int] = {1, total_lines + 1}
        if symbols:
            for s in symbols:
                if 1 <= s.line_start <= total_lines:
                    boundary_lines.add(s.line_start)
                if 1 <= s.line_end <= total_lines:
                    boundary_lines.add(s.line_end + 1)

        sorted_boundaries = sorted(list(boundary_lines))
        chunks: List[CodeChunk] = []

        curr_start_line = 1
        curr_buffer_lines: List[str] = []
        curr_char_count = 0
        chunk_idx = 0

        line_num = 1
        while line_num <= total_lines:
            line_text = lines[line_num - 1]
            curr_buffer_lines.append(line_text)
            curr_char_count += len(line_text)

            # Check if we should split at this line
            is_boundary = (line_num + 1) in boundary_lines
            exceeds_size = curr_char_count >= self.target_chunk_size

            if (is_boundary and curr_char_count >= self.target_chunk_size * 0.7) or exceeds_size:
                chunk_content = "".join(curr_buffer_lines)
                chunks.append(
                    CodeChunk(
                        file_path=file_path,
                        chunk_index=chunk_idx,
                        line_start=curr_start_line,
                        line_end=line_num,
                        content=chunk_content,
                    )
                )
                chunk_idx += 1

                # Calculate overlap lines
                overlap_lines: List[str] = []
                overlap_chars = 0
                for rev_line in reversed(curr_buffer_lines):
                    if overlap_chars + len(rev_line) <= self.overlap_chars:
                        overlap_lines.insert(0, rev_line)
                        overlap_chars += len(rev_line)
                    else:
                        break

                curr_start_line = max(1, line_num - len(overlap_lines) + 1)
                curr_buffer_lines = list(overlap_lines)
                curr_char_count = overlap_chars

            line_num += 1

        # Flush any remaining buffer
        if curr_buffer_lines:
            chunk_content = "".join(curr_buffer_lines)
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    chunk_index=chunk_idx,
                    line_start=curr_start_line,
                    line_end=total_lines,
                    content=chunk_content,
                )
            )

        return chunks
