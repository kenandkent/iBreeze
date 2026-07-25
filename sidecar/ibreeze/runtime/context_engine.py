"""Context Pack building and token budget management."""

from __future__ import annotations

from typing import Any


class ContextEngine:
    """Manages context window packing for agent runs."""

    def __init__(self, max_tokens: int = 128_000) -> None:
        self._max_tokens = max_tokens
        self._used_tokens = 0
        self._messages: list[dict[str, Any]] = []

    def add_message(self, role: str, content: str, *, estimated_tokens: int | None = None) -> None:
        """Add a message to the context."""
        tokens = estimated_tokens or self._estimate_tokens(content)
        self._messages.append({"role": role, "content": content, "tokens": tokens})
        self._used_tokens += tokens

    def add_system_prompt(self, content: str) -> None:
        """Add system prompt (always included, never truncated)."""
        tokens = self._estimate_tokens(content)
        self._messages.insert(
            0, {"role": "system", "content": content, "tokens": tokens, "pinned": True}
        )
        self._used_tokens += tokens

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Add tool result."""
        self.add_message("tool", content)

    def get_context(self) -> list[dict[str, str]]:
        """Get the context window, truncating oldest non-pinned messages if needed."""
        result: list[dict[str, str]] = []
        budget = self._max_tokens
        for msg in reversed(self._messages):
            if msg.get("pinned") or budget >= msg["tokens"]:
                result.insert(0, {"role": msg["role"], "content": msg["content"]})
                budget -= msg["tokens"]
        return result

    def get_token_usage(self) -> dict[str, int]:
        """Get current token usage stats."""
        return {
            "max_tokens": self._max_tokens,
            "used_tokens": self._used_tokens,
            "remaining_tokens": max(self._max_tokens - self._used_tokens, 0),
            "message_count": len(self._messages),
        }

    def truncate_to_budget(self) -> int:
        """Truncate oldest messages to fit budget. Returns tokens removed."""
        removed = 0
        while self._used_tokens > self._max_tokens and len(self._messages) > 1:
            # Don't remove pinned messages or the last message
            for i in range(len(self._messages) - 1, 0, -1):
                if not self._messages[i].get("pinned"):
                    removed += self._messages[i]["tokens"]
                    self._used_tokens -= self._messages[i]["tokens"]
                    self._messages.pop(i)
                    break
            else:
                break
        return removed

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimation (≈ 4 chars per token)."""
        return max(len(text) // 4, 1)
