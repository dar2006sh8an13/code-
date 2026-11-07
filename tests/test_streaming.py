"""Unit tests for the streaming engine using mocked Ollama responses."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from ollama import ResponseError

from codeagent.llm.client import (
    ModelNotFoundError,
    OllamaConnectionError,
    OllamaTimeoutError,
)
from codeagent.llm.streaming import StreamingEngine


class TestStreamingEngine:
    """Test suite for StreamingEngine chunk processing and error handling."""

    def test_streaming_chunk_processing(self) -> None:
        """Verify stream yields individual text delta chunks correctly."""
        mock_chunks = [
            MagicMock(message=MagicMock(content="Hello")),
            MagicMock(message=MagicMock(content=" ")),
            MagicMock(message=MagicMock(content="world")),
            MagicMock(message=MagicMock(content="!")),
        ]

        mock_client = MagicMock()
        mock_client.chat.return_value = iter(mock_chunks)

        engine = StreamingEngine()
        chunks = list(
            engine.iter_stream_chunks(
                client=mock_client,
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3:latest",
                temperature=0.2,
                max_output_tokens=100,
            )
        )

        assert chunks == ["Hello", " ", "world", "!"]
        mock_client.chat.assert_called_once_with(
            model="qwen3:latest",
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
            options={"temperature": 0.2, "num_predict": 100},
        )

    def test_streaming_chat_accumulates_and_displays(self) -> None:
        """Verify stream_chat accumulates full text and calls chunk callbacks."""
        mock_chunks = [
            MagicMock(message=MagicMock(content="Python ")),
            MagicMock(message=MagicMock(content="is ")),
            MagicMock(message=MagicMock(content="great")),
        ]

        mock_client = MagicMock()
        mock_client.chat.return_value = iter(mock_chunks)

        captured_chunks: list[str] = []
        engine = StreamingEngine()

        result = engine.stream_chat(
            client=mock_client,
            messages=[{"role": "user", "content": "say something"}],
            model="qwen3:latest",
            display=False,
            on_chunk=lambda c: captured_chunks.append(c),
        )

        assert result == "Python is great"
        assert captured_chunks == ["Python ", "is ", "great"]

    def test_streaming_connection_error_handling(self) -> None:
        """Verify network errors raise OllamaConnectionError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = httpx.ConnectError("Connection refused")

        engine = StreamingEngine()
        with pytest.raises(OllamaConnectionError, match="Cannot connect to Ollama server"):
            list(
                engine.iter_stream_chunks(
                    client=mock_client,
                    messages=[{"role": "user", "content": "hi"}],
                    model="qwen3:latest",
                )
            )

    def test_streaming_model_not_found_handling(self) -> None:
        """Verify 404 response raises ModelNotFoundError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = ResponseError("model missing not found", status_code=404)

        engine = StreamingEngine()
        with pytest.raises(ModelNotFoundError, match="is not installed in Ollama"):
            list(
                engine.iter_stream_chunks(
                    client=mock_client,
                    messages=[{"role": "user", "content": "hi"}],
                    model="missing:latest",
                )
            )

    def test_streaming_timeout_handling(self) -> None:
        """Verify read timeouts raise OllamaTimeoutError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = httpx.ReadTimeout("Stream timed out")

        engine = StreamingEngine()
        with pytest.raises(OllamaTimeoutError, match="Stream connection timed out"):
            list(
                engine.iter_stream_chunks(
                    client=mock_client,
                    messages=[{"role": "user", "content": "hi"}],
                    model="qwen3:latest",
                )
            )

    def test_streaming_thinking_suppressed_by_default(self) -> None:
        """Verify internal reasoning/thinking chunks are suppressed from output by default."""
        mock_chunks = [
            MagicMock(message=MagicMock(content="", thinking="Let me think about how to build a calculator...")),
            MagicMock(message=MagicMock(content="", reasoning_content="User wants HTML code...")),
            MagicMock(message=MagicMock(content="```html\n", thinking="")),
            MagicMock(message=MagicMock(content="<h1>Calculator</h1>\n", thinking="")),
            MagicMock(message=MagicMock(content="```", thinking="")),
        ]

        mock_client = MagicMock()
        mock_client.chat.return_value = iter(mock_chunks)

        engine = StreamingEngine()
        chunks = list(
            engine.iter_stream_chunks(
                client=mock_client,
                messages=[{"role": "user", "content": "create calculator"}],
                model="qwen3:latest",
                include_thinking=False,
            )
        )

        assert chunks == ["```html\n", "<h1>Calculator</h1>\n", "```"]
        full_text = "".join(chunks)
        assert "think" not in full_text
        assert "reasoning" not in full_text

    def test_streaming_think_tags_filtered(self) -> None:
        """Verify <think>...</think> tags inside content are stripped when include_thinking=False."""
        mock_chunks = [
            MagicMock(message=MagicMock(content="<think>Planning the implementation</think>```html")),
            MagicMock(message=MagicMock(content="\n<div>Test</div>\n")),
            MagicMock(message=MagicMock(content="```")),
        ]

        mock_client = MagicMock()
        mock_client.chat.return_value = iter(mock_chunks)

        engine = StreamingEngine()
        chunks = list(
            engine.iter_stream_chunks(
                client=mock_client,
                messages=[{"role": "user", "content": "build app"}],
                model="qwen3:latest",
                include_thinking=False,
            )
        )

        assert "".join(chunks) == "```html\n<div>Test</div>\n```"

