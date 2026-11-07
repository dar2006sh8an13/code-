"""Unit tests for boundary-preserving code chunking."""

from pathlib import Path
import pytest

from codeagent.indexing.chunker import CodeChunk, CodeChunker


def test_chunker_basic() -> None:
    """Verify chunker partitions source code with line ranges and content hashes."""
    code = "\n".join([f"line_{i} = {i}" for i in range(1, 101)])
    chunker = CodeChunker(chunk_size=300, overlap=50)

    chunks = chunker.chunk_text(content=code, file_path="script.py")

    assert len(chunks) > 1
    for idx, c in enumerate(chunks):
        assert c.chunk_index == idx
        assert c.file_path == "script.py"
        assert c.line_start <= c.line_end
        assert len(c.content_hash) == 64  # SHA-256


def test_chunker_preserves_small_file_single_chunk() -> None:
    """Verify small file is retained as a single chunk."""
    small_code = "def hello():\n    return 'world'\n"
    chunker = CodeChunker(chunk_size=1000, overlap=100)

    chunks = chunker.chunk_text(content=small_code, file_path="small.py")
    assert len(chunks) == 1
    assert chunks[0].line_start == 1
    assert chunks[0].content == small_code

