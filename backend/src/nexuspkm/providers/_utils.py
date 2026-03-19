"""Shared helpers used across all provider implementations."""

from typing import Any

try:
    from llama_index.core.llms import ChatMessage, MessageRole
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install llama-index-core to use providers") from exc


def to_chat_messages(messages: list[dict[str, str]]) -> list[Any]:
    """Convert a list of role/content dicts to LlamaIndex ChatMessage objects."""
    return [ChatMessage(role=MessageRole(m["role"]), content=m["content"]) for m in messages]


def extract_tokens(raw: dict[str, Any]) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a raw provider response dict.

    Handles field-name differences between Bedrock (inputTokens/outputTokens)
    and OpenAI-compatible APIs (prompt_tokens/completion_tokens).
    Returns (0, 0) when usage info is absent.
    """
    usage = raw.get("usage", {})
    input_tokens = int(
        usage.get("inputTokens") or usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    )
    output_tokens = int(
        usage.get("outputTokens")
        or usage.get("completion_tokens")
        or usage.get("output_tokens")
        or 0
    )
    return input_tokens, output_tokens
