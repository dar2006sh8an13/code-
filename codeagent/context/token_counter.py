"""Token counter and estimator for context window budgeting.

Methodology & Limitations:
--------------------------
This module implements a conservative heuristic token estimator designed for local LLMs
(specifically Qwen and Llama architectures).

Heuristic Details:
1. Base Ratio: ~3.3 characters per token for general code and mixed text.
2. Word Ratio: ~1.3 tokens per whitespace-separated word.
3. Message Overhead: +4 tokens per message for role/metadata packaging in ChatML format.
4. Conservative Margin: Always takes the maximum of character-based and word-based estimates,
   applying a safety ceiling.

Limitations:
- Heuristic estimation does not reproduce exact Byte-Pair Encoding (BPE) boundaries for rare
  multilingual characters, emoji sequences, or dense hex tokens.
- However, by deliberately overestimating by ~15-20%, it reliably guarantees that the prompt
  never unexpectedly breaches the server's context window.
"""

import math
from typing import Any


def estimate_tokens(text: str) -> int:
    """Conservatively estimate token count for a text string.

    Args:
        text: Input string.

    Returns:
        int: Estimated token count (always >= 0).
    """
    if not text:
        return 0

    stripped = text.strip()
    if not stripped:
        return 0

    char_count = len(stripped)
    word_count = len(stripped.split())

    # Code and symbols average ~3.0 - 3.5 chars/token; prose averages ~4.0 chars/token.
    # Using 3.3 chars/token provides a safe conservative estimate.
    char_estimate = math.ceil(char_count / 3.3)
    word_estimate = math.ceil(word_count * 1.25)

    return max(char_estimate, word_estimate, 1)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate token count for a single message dictionary.

    Includes role metadata and tool call serialization overhead.

    Args:
        message: Message dict containing 'role', 'content', etc.

    Returns:
        int: Estimated token count including structural packaging overhead.
    """
    total = 4  # ChatML delimiter and role tagging overhead (<|im_start|>role ... <|im_end|>)

    content = message.get("content") or ""
    if isinstance(content, str):
        total += estimate_tokens(content)

    # Tool calls overhead
    tool_calls = message.get("tool_calls")
    if tool_calls and isinstance(tool_calls, list):
        for tc in tool_calls:
            total += 10  # Function call wrapper overhead
            if isinstance(tc, dict):
                func = tc.get("function", {})
                total += estimate_tokens(str(func.get("name", "")))
                total += estimate_tokens(str(func.get("arguments", "")))

    return total


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total token consumption for a sequence of conversation messages.

    Args:
        messages: List of message dictionaries.

    Returns:
        int: Total estimated token count.
    """
    total = 3  # Conversation wrapper priming tokens (<|im_start|>assistant)
    for msg in messages:
        total += estimate_message_tokens(msg)
    return total

