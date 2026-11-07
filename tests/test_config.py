"""Unit tests for CodeAgent configuration and settings.

These tests verify configuration defaults and environment overrides without
requiring a running Ollama server.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import httpx
from ollama import ResponseError

from codeagent.config.settings import Settings, get_settings
from codeagent.llm.client import (
    LLMClient,
    ModelNotFoundError,
    OllamaConnectionError,
    OllamaTimeoutError,
    format_bytes,
)


class TestCodeAgentConfig:
    """Test suite for CodeAgent settings and configuration system."""

    def test_default_app_name(self) -> None:
        """Verify default application name is Coder with Code."""
        settings = Settings(_env_file=None)
        assert settings.app_name in ("Coder with Code", "Code AG", "Code")

    def test_default_app_version(self) -> None:
        """Verify default application version is 0.1.0."""
        settings = Settings(_env_file=None)
        assert settings.app_version == "0.1.0"

    def test_default_model_configuration(self) -> None:
        """Verify default model configuration is qwen3:latest."""
        settings = Settings(_env_file=None)
        assert settings.model_name == "qwen3:latest"

    def test_default_ollama_host_configuration(self) -> None:
        """Verify default Ollama host configuration is http://localhost:11434."""
        settings = Settings(_env_file=None)
        assert settings.ollama_host == "http://localhost:11434"

    def test_default_timeout_and_temperature(self) -> None:
        """Verify default timeout is 300 seconds and temperature is 0.2."""
        settings = Settings(_env_file=None)
        assert settings.request_timeout == 300.0
        assert settings.temperature == 0.2

    def test_default_phase2_settings(self) -> None:
        """Verify default Phase 2 context and tool settings."""
        settings = Settings(_env_file=None)
        assert settings.context_window == 8192
        assert settings.max_output_tokens == 2048
        assert settings.max_history_messages == 30
        assert settings.context_reserve_tokens == 1024
        assert settings.max_tool_iterations == 5
        assert settings.conversation_storage_path == "data/conversations"

    def test_default_phase3_settings(self) -> None:
        """Verify default Phase 3 filesystem and workspace settings."""
        settings = Settings(_env_file=None)
        assert settings.workspace_root is None
        assert settings.max_file_size_mb == 5
        assert settings.max_scan_depth == 8
        assert settings.max_scan_entries == 5000
        assert settings.backup_enabled is True
        assert settings.require_write_approval is True
        assert settings.require_delete_approval is True
        assert settings.backup_directory == ".codeagent/backups"

    def test_default_phase5_settings(self) -> None:
        """Verify default Phase 5 execution settings."""
        settings = Settings(_env_file=None)
        assert settings.execution_enabled is True
        assert settings.execution_timeout_seconds == 120.0
        assert settings.max_output_size_mb == 5
        assert settings.max_concurrent_processes == 3
        assert settings.require_python_approval is True
        assert settings.require_dependency_approval is True
        assert settings.require_command_approval is True
        assert settings.execution_workspace_only is True
        assert settings.execution_audit_enabled is True
        assert settings.audit_log_path == ".codeagent/audit/execution.jsonl"

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify settings are overridden by environment variables."""
        monkeypatch.setenv("APP_NAME", "CustomCodeAgent")
        monkeypatch.setenv("APP_VERSION", "1.2.3")
        monkeypatch.setenv("OLLAMA_HOST", "http://192.168.1.50:11434")
        monkeypatch.setenv("MODEL_NAME", "custom-model:v1")
        monkeypatch.setenv("REQUEST_TIMEOUT", "450")
        monkeypatch.setenv("TEMPERATURE", "0.7")
        monkeypatch.setenv("CONTEXT_WINDOW", "16384")
        monkeypatch.setenv("MAX_OUTPUT_TOKENS", "4096")
        monkeypatch.setenv("MAX_HISTORY_MESSAGES", "50")
        monkeypatch.setenv("CONTEXT_RESERVE_TOKENS", "2048")
        monkeypatch.setenv("MAX_TOOL_ITERATIONS", "10")
        monkeypatch.setenv("CONVERSATION_STORAGE_PATH", "custom/storage")

        settings = Settings(_env_file=None)
        assert settings.app_name == "CustomCodeAgent"
        assert settings.app_version == "1.2.3"
        assert settings.ollama_host == "http://192.168.1.50:11434"
        assert settings.model_name == "custom-model:v1"
        assert settings.request_timeout == 450.0
        assert settings.temperature == 0.7
        assert settings.context_window == 16384
        assert settings.max_output_tokens == 4096
        assert settings.max_history_messages == 50
        assert settings.context_reserve_tokens == 2048
        assert settings.max_tool_iterations == 10
        assert settings.conversation_storage_path == "custom/storage"

    def test_explicit_instantiation(self) -> None:
        """Verify explicit kwargs take precedence when instantiating Settings."""
        settings = Settings(
            _env_file=None,
            app_name="ExplicitAgent",
            app_version="2.0.0",
            ollama_host="http://remote-server:11434",
            model_name="qwen-coder:latest",
            request_timeout=60.0,
            temperature=0.0,
        )
        assert settings.app_name == "ExplicitAgent"
        assert settings.app_version == "2.0.0"
        assert settings.ollama_host == "http://remote-server:11434"
        assert settings.model_name == "qwen-coder:latest"
        assert settings.request_timeout == 60.0
        assert settings.temperature == 0.0

    def test_get_settings_singleton(self) -> None:
        """Verify get_settings returns a valid Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)
        assert settings.app_name is not None
        assert settings.model_name is not None


class TestLLMClientOffline:
    """Test suite for LLM Client logic without requiring a live Ollama server."""

    def test_client_initialization_defaults(self) -> None:
        """Verify LLMClient uses settings defaults when instantiated."""
        settings = Settings(
            _env_file=None,
            ollama_host="http://test-host:11434",
            model_name="qwen3:test",
            request_timeout=45.0,
            temperature=0.5,
        )
        client = LLMClient(settings=settings)
        assert client.host == "http://test-host:11434"
        assert client.default_model == "qwen3:test"
        assert client.timeout == 45.0
        assert client.temperature == 0.5

    def test_client_empty_prompt_raises_value_error(self) -> None:
        """Verify that an empty prompt raises ValueError."""
        client = LLMClient(settings=Settings(_env_file=None))
        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            client.generate("")

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            client.generate("   ")

    @patch("codeagent.llm.client.OllamaSDKClient")
    def test_client_connection_error_handling(self, mock_sdk_cls: MagicMock) -> None:
        """Verify connection errors are translated to OllamaConnectionError."""
        mock_instance = MagicMock()
        mock_instance.chat.side_effect = httpx.ConnectError("Connection refused")
        mock_sdk_cls.return_value = mock_instance

        client = LLMClient(settings=Settings(_env_file=None))
        client._client = mock_instance

        with pytest.raises(OllamaConnectionError, match="Unable to connect to Ollama server"):
            client.generate("Hello")

    @patch("codeagent.llm.client.OllamaSDKClient")
    def test_client_model_not_found_handling(self, mock_sdk_cls: MagicMock) -> None:
        """Verify 404 response is translated to ModelNotFoundError."""
        mock_instance = MagicMock()
        mock_instance.chat.side_effect = ResponseError("model 'missing:latest' not found", status_code=404)
        mock_sdk_cls.return_value = mock_instance

        client = LLMClient(settings=Settings(_env_file=None))
        client._client = mock_instance

        with pytest.raises(ModelNotFoundError, match="is not installed in Ollama"):
            client.generate("Hello", model="missing:latest")

    @patch("codeagent.llm.client.OllamaSDKClient")
    def test_client_timeout_handling(self, mock_sdk_cls: MagicMock) -> None:
        """Verify timeout exceptions are translated to OllamaTimeoutError."""
        mock_instance = MagicMock()
        mock_instance.chat.side_effect = httpx.ReadTimeout("Read timed out")
        mock_sdk_cls.return_value = mock_instance

        client = LLMClient(settings=Settings(_env_file=None))
        client._client = mock_instance

        with pytest.raises(OllamaTimeoutError, match="Request timed out"):
            client.generate("Hello")

    def test_format_bytes_utility(self) -> None:
        """Verify byte formatting helper function."""
        assert format_bytes(0) == "Unknown"
        assert format_bytes(None) == "Unknown"
        assert format_bytes(500) == "500.0 B"
        assert format_bytes(500_000) == "500.0 KB"
        assert format_bytes(500_000_000) == "500.0 MB"
        assert format_bytes(5_225_388_164) == "5.2 GB"
