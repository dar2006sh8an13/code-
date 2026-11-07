"""Integration tests for live local Ollama server and Qwen3 model (optional / skipped if offline)."""

import pytest
import httpx

from codeagent.config.settings import get_settings
from codeagent.llm.client import LLMClient
from codeagent.llm.streaming import StreamingEngine
from codeagent.llm.structured import ErrorAnalysis, StructuredResponseEngine
from codeagent.tools.executor import ToolExecutor


def is_ollama_online() -> bool:
    """Check if local Ollama server is responding."""
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not is_ollama_online(),
        reason="Local Ollama server is offline; skipping live integration tests."
    )
]


class TestLiveOllamaIntegration:
    """Live integration tests running against local Ollama server."""

    def test_live_streaming_generation(self) -> None:
        """Verify real-time streaming against live Ollama."""
        client = LLMClient()
        engine = StreamingEngine()

        chunks: list[str] = []
        result = engine.stream_chat(
            client=client._client,
            messages=[{"role": "user", "content": "Respond with the word 'OK' only."}],
            model=client.default_model,
            max_output_tokens=512,
            display=False,
            on_chunk=lambda c: chunks.append(c),
        )

        assert len(chunks) > 0
        assert len(result.strip()) > 0

    def test_live_tool_calling(self) -> None:
        """Verify end-to-end tool calling with Qwen3."""
        client = LLMClient()
        executor = ToolExecutor()

        final_text, _ = executor.run_tool_loop(
            client=client._client,
            model=client.default_model,
            messages=[{"role": "user", "content": "What is 15 + 25?"}],
            max_iterations=3,
        )

        assert "40" in final_text

    def test_live_structured_json(self) -> None:
        """Verify live structured JSON generation and Pydantic validation."""
        client = LLMClient()
        engine = StructuredResponseEngine()

        analysis = engine.generate_structured(
            client=client._client,
            prompt="Analyze this error: ZeroDivisionError: division by zero in calculate() line 10",
            schema_class=ErrorAnalysis,
            model=client.default_model,
        )

        assert isinstance(analysis, ErrorAnalysis)
        assert analysis.error_type is not None
        assert analysis.cause is not None
        assert analysis.solution is not None

    def test_live_filesystem_tool_calling(self, tmp_path) -> None:
        """Verify end-to-end filesystem tool calling with Qwen3."""
        from codeagent.filesystem.manager import FilesystemManager
        from codeagent.tools.registry import get_default_registry

        # Setup test file in isolated tmp_path
        test_file = tmp_path / "greeting.txt"
        test_file.write_text("Hello from Phase 3!", encoding="utf-8")

        client = LLMClient()
        fs_mgr = FilesystemManager(workspace_root=tmp_path)
        registry = get_default_registry(filesystem_manager=fs_mgr)
        executor = ToolExecutor(registry=registry)

        final_text, _ = executor.run_tool_loop(
            client=client._client,
            model=client.default_model,
            messages=[{"role": "user", "content": "Read the file greeting.txt and tell me what it says."}],
            max_iterations=3,
        )

        assert "Hello" in final_text or "greeting" in final_text.lower()
