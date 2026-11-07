"""Unit tests for conversation state, history, and storage."""

import json
from pathlib import Path

import pytest

from codeagent.conversation.manager import Conversation, ConversationManager, Message
from codeagent.conversation.storage import (
    ConversationNotFoundError,
    ConversationStorage,
    CorruptedConversationError,
    StorageError,
    scrub_secrets,
)


class TestConversationManager:
    """Test suite for Conversation and ConversationManager."""

    def test_conversation_creation(self) -> None:
        """Verify new conversation has a unique ID and initialized empty or with system prompt."""
        mgr = ConversationManager(system_prompt="You are a helpful coding assistant.")
        conv = mgr.active_conversation

        assert conv.id.startswith("conv_")
        assert len(conv.messages) == 1
        assert conv.messages[0].role == "system"
        assert conv.messages[0].content == "You are a helpful coding assistant."

    def test_message_addition_and_llm_format(self) -> None:
        """Verify adding messages updates history and produces valid LLM format."""
        mgr = ConversationManager()
        mgr.add_user_message("What is Python?")
        mgr.add_assistant_message("Python is a programming language.")
        mgr.add_tool_message("100", tool_name="add")

        llm_messages = mgr.get_messages_for_llm()
        assert len(llm_messages) == 3
        assert llm_messages[0] == {"role": "user", "content": "What is Python?"}
        assert llm_messages[1] == {"role": "assistant", "content": "Python is a programming language."}
        assert llm_messages[2] == {"role": "tool", "content": "100", "name": "add"}

    def test_conversation_clear(self) -> None:
        """Verify clear resets history while preserving system prompt."""
        mgr = ConversationManager(system_prompt="System anchor")
        mgr.add_user_message("Hello")
        mgr.add_assistant_message("Hi")
        assert len(mgr.active_conversation.messages) == 3

        mgr.clear()
        assert len(mgr.active_conversation.messages) == 1
        assert mgr.active_conversation.messages[0].role == "system"

    def test_save_and_load_cycle(self, tmp_path: Path) -> None:
        """Verify conversation can be saved and accurately reloaded."""
        mgr = ConversationManager(storage_path=tmp_path)
        mgr.add_user_message("First question")
        mgr.add_assistant_message("First answer")

        saved_path = mgr.save("my_test_chat")
        assert saved_path.exists()

        # Load in a fresh manager instance
        fresh_mgr = ConversationManager(storage_path=tmp_path)
        loaded_conv = fresh_mgr.load("my_test_chat")

        assert loaded_conv.id == mgr.active_conversation.id
        assert len(loaded_conv.messages) == 2
        assert loaded_conv.messages[0].content == "First question"
        assert loaded_conv.messages[1].content == "First answer"


class TestConversationStorage:
    """Test suite for ConversationStorage persistence and security."""

    def test_secret_scrubbing(self) -> None:
        """Verify sensitive tokens and keys are masked before writing to storage."""
        sensitive_text = "Here is my api_key: sk-1234567890abcdef1234567890abcdef and Bearer secret_token_value_xyz"
        scrubbed = scrub_secrets(sensitive_text)

        assert "sk-1234567890abcdef1234567890abcdef" not in scrubbed
        assert "secret_token_value_xyz" not in scrubbed
        assert "[REDACTED_SECRET]" in scrubbed

    def test_corrupted_file_handling(self, tmp_path: Path) -> None:
        """Verify corrupted JSON files raise CorruptedConversationError without crashing listing."""
        storage = ConversationStorage(tmp_path)

        # Write corrupted invalid JSON
        corrupt_file = tmp_path / "corrupted_chat.json"
        corrupt_file.write_text("{ this is not valid json !!! }", encoding="utf-8")

        # Loading corrupt file directly raises CorruptedConversationError
        with pytest.raises(CorruptedConversationError):
            storage.load("corrupted_chat")

        # Listing gracefully skips corrupted files
        saved_list = storage.list_saved()
        assert len(saved_list) == 0

    def test_not_found_handling(self, tmp_path: Path) -> None:
        """Verify non-existent file raises ConversationNotFoundError."""
        storage = ConversationStorage(tmp_path)
        with pytest.raises(ConversationNotFoundError):
            storage.load("non_existent_conversation_id")

    def test_path_traversal_protection(self, tmp_path: Path) -> None:
        """Verify path traversal attempts are safely rejected."""
        storage = ConversationStorage(tmp_path)
        with pytest.raises(StorageError):
            storage.save({"id": "test"}, identifier="../../system_file")

