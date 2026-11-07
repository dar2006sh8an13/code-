"""Unit tests for token estimation, context window budgeting, and history trimming."""

import pytest

from codeagent.context.manager import ContextBudgetExceededError, ContextManager
from codeagent.context.token_counter import (
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
)


class TestTokenCounter:
    """Test suite for conservative token estimation."""

    def test_empty_string_tokens(self) -> None:
        """Verify empty string estimation returns 0."""
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") == 0

    def test_text_token_estimation(self) -> None:
        """Verify reasonable conservative token estimation."""
        text = "def calculate_factorial(n: int) -> int:"
        tokens = estimate_tokens(text)
        assert tokens > 0
        # Character count is 39 chars; estimate should be ~10-15 tokens
        assert 8 <= tokens <= 20

    def test_message_token_estimation(self) -> None:
        """Verify message overhead is included."""
        msg = {"role": "user", "content": "Hello world"}
        tokens = estimate_message_tokens(msg)
        # Content is ~3-4 tokens + 4 overhead
        assert tokens >= 7


class TestContextManager:
    """Test suite for ContextManager budget enforcement and history trimming."""

    def test_budget_calculation(self) -> None:
        """Verify available input budget calculation."""
        # 8192 - 2048 - 1024 = 5120
        cm = ContextManager(
            context_window=8192,
            max_output_tokens=2048,
            context_reserve_tokens=1024,
            max_history_messages=30,
        )
        assert cm.available_input_budget == 5120

    def test_system_prompt_and_latest_turn_preserved(self) -> None:
        """Verify system prompt and the latest user turn are always preserved."""
        cm = ContextManager(
            context_window=2000,
            max_output_tokens=500,
            context_reserve_tokens=200,
            max_history_messages=5,
        )

        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer 2"},
            {"role": "user", "content": "Final latest question"},
        ]

        fitted = cm.fit_messages(messages, system_prompt="CRITICAL_SYSTEM_INSTRUCTION")

        # First message must be system
        assert fitted[0]["role"] == "system"
        assert fitted[0]["content"] == "CRITICAL_SYSTEM_INSTRUCTION"

        # Last message must be the latest user question
        assert fitted[-1]["role"] == "user"
        assert fitted[-1]["content"] == "Final latest question"

    def test_history_message_count_trimming(self) -> None:
        """Verify max_history_messages limit trims older turns."""
        cm = ContextManager(
            context_window=10000,
            max_output_tokens=1000,
            context_reserve_tokens=500,
            max_history_messages=3,  # Only retain 3 recent turns
        )

        messages = [
            {"role": "user", "content": "Old Q1"},
            {"role": "assistant", "content": "Old A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
        ]

        fitted = cm.fit_messages(messages)
        # Should be trimmed to at most 3 turns (Q2, A2, Q3)
        assert len(fitted) == 3
        assert fitted[0]["content"] == "Q2"
        assert fitted[-1]["content"] == "Q3"

    def test_token_budget_pruning(self) -> None:
        """Verify large messages are pruned when token budget is tight."""
        # Create a small budget
        cm = ContextManager(
            context_window=1500,
            max_output_tokens=500,
            context_reserve_tokens=200,
            # Budget is 1500 - 500 - 200 = 800 tokens
            max_history_messages=20,
        )

        large_text = "word " * 800  # ~1200 tokens (exceeds budget)
        messages = [
            {"role": "user", "content": f"Early {large_text}"},
            {"role": "assistant", "content": "Short reply"},
            {"role": "user", "content": "Latest brief query"},
        ]

        fitted = cm.fit_messages(messages, system_prompt="System rules")

        # The early massive message must be trimmed to respect the 800 token budget
        assert fitted[0]["role"] == "system"
        assert fitted[-1]["content"] == "Latest brief query"
        assert not any("Early" in m["content"] for m in fitted)

    def test_oversized_system_prompt_raises_budget_error(self) -> None:
        """Verify oversized system instructions exceeding total budget raise ContextBudgetExceededError."""
        cm = ContextManager(
            context_window=1000,
            max_output_tokens=400,
            context_reserve_tokens=100,  # Budget = 500
        )
        massive_prompt = "system rule " * 600  # >700 tokens

        with pytest.raises(ContextBudgetExceededError):
            cm.fit_messages([], system_prompt=massive_prompt)
