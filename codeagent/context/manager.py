"""Context window budgeting, token management, and message history trimming."""

from typing import Any, Optional

from codeagent.config.settings import Settings, get_settings
from codeagent.context.token_counter import (
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
)


class ContextBudgetExceededError(Exception):
    """Raised when essential prompt content exceeds the available context window."""
    pass


class ContextManager:
    """Enforces token budgets and prunes history to prevent exceeding model limits."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        context_window: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        max_history_messages: Optional[int] = None,
        context_reserve_tokens: Optional[int] = None,
    ) -> None:
        """Initialize the context manager.

        Args:
            settings: Optional application settings.
            context_window: Total context window size in tokens.
            max_output_tokens: Tokens reserved for model output generation.
            max_history_messages: Maximum count of historical turns to keep.
            context_reserve_tokens: Safety token margin for prompt overhead.
        """
        cfg = settings or get_settings()
        self.context_window = context_window or cfg.context_window
        self.max_output_tokens = max_output_tokens or cfg.max_output_tokens
        self.max_history_messages = max_history_messages or cfg.max_history_messages
        self.context_reserve_tokens = context_reserve_tokens or cfg.context_reserve_tokens

    @property
    def available_input_budget(self) -> int:
        """Maximum tokens allowed for the entire prompt history."""
        budget = self.context_window - self.max_output_tokens - self.context_reserve_tokens
        return max(budget, 512)

    def get_budget_status(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute current token utilization statistics.

        Args:
            messages: List of message dictionaries.

        Returns:
            dict: Summary containing used tokens, budget, remaining tokens, and utilization %.
        """
        used_tokens = estimate_messages_tokens(messages)
        remaining = self.available_input_budget - used_tokens
        percent_used = round((used_tokens / self.available_input_budget) * 100, 1)

        return {
            "used_tokens": used_tokens,
            "input_budget": self.available_input_budget,
            "remaining_tokens": max(0, remaining),
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "percent_used": percent_used,
            "message_count": len(messages),
        }

    def fit_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fit messages within the context budget and message limit without truncating system prompt.

        Algorithm:
        1. Extract and preserve the system prompt (never truncated).
        2. Ensure the most recent user message is preserved.
        3. Enforce max_history_messages limit by taking the most recent turns.
        4. Progressively trim older non-system messages until the total token count
           is within available_input_budget.

        Args:
            messages: Full list of conversation message dictionaries.
            system_prompt: Optional explicit system prompt override.

        Returns:
            list[dict[str, Any]]: Fitted messages respecting all constraints.

        Raises:
            ContextBudgetExceededError: If the system prompt alone exceeds the entire budget.
        """
        if not messages and not system_prompt:
            return []

        # 1. Identify system instructions
        system_messages: list[dict[str, Any]] = []
        conversation_turns: list[dict[str, Any]] = []

        if system_prompt and system_prompt.strip():
            system_messages.append({"role": "system", "content": system_prompt.strip()})

        for msg in messages:
            if msg.get("role") == "system":
                if not system_prompt:  # Use existing system message if no override supplied
                    system_messages.append(msg)
            else:
                conversation_turns.append(msg)

        system_cost = estimate_messages_tokens(system_messages) if system_messages else 0
        if system_cost > self.available_input_budget:
            raise ContextBudgetExceededError(
                f"System instructions consume {system_cost} tokens, exceeding the available "
                f"input budget of {self.available_input_budget} tokens."
            )

        # 2. Enforce max_history_messages limit on conversation turns
        if len(conversation_turns) > self.max_history_messages:
            conversation_turns = conversation_turns[-self.max_history_messages :]

        # 3. Always preserve the latest message (usually the active user prompt)
        if not conversation_turns:
            return system_messages

        latest_turn = conversation_turns[-1]
        history_pool = conversation_turns[:-1]

        # Calculate budget remaining for history
        budget_for_history = (
            self.available_input_budget - system_cost - estimate_message_tokens(latest_turn)
        )

        fitted_history: list[dict[str, Any]] = []
        current_cost = 0

        # Progressively add history backwards (newest to oldest)
        for turn in reversed(history_pool):
            turn_cost = estimate_message_tokens(turn)
            if current_cost + turn_cost <= budget_for_history:
                fitted_history.insert(0, turn)
                current_cost += turn_cost
            else:
                # History limit reached; stop including older messages
                break

        # Assemble final sequence: system messages -> fitted history -> latest turn
        result: list[dict[str, Any]] = []
        result.extend(system_messages)
        result.extend(fitted_history)
        result.append(latest_turn)

        return result

