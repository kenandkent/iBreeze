"""Token budget calculation for model calls."""

from __future__ import annotations

# Default context-window limits by model family prefix.
MODEL_LIMITS: dict[str, int] = {
    "gpt-4": 128_000,
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "claude-3": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
    "deepseek": 64_000,
}

_DEFAULT_LIMIT = 128_000


def calculate_budget(
    context_window: int,
    max_output_tokens: int,
) -> dict[str, int]:
    """Calculate token budget per spec.

    output_reserve = min(max_output_tokens, floor(context_window * 0.20))
    available = context_window - output_reserve
    system_reserve = floor(available * 0.10)
    user_budget = available - system_reserve
    """
    output_reserve = min(max_output_tokens, int(context_window * 0.20))
    available = context_window - output_reserve
    system_reserve = int(available * 0.10)
    user_budget = available - system_reserve

    return {
        "context_window": context_window,
        "output_reserve": output_reserve,
        "system_reserve": system_reserve,
        "user_budget": user_budget,
    }


def truncate_to_budget(text: str, max_tokens: int, *, from_end: bool = True) -> str:
    """Truncate text to fit within token budget (≈ 4 chars per token)."""
    estimated_tokens = max(len(text) // 4, 1)
    if estimated_tokens <= max_tokens:
        return text
    max_chars = max_tokens * 4
    if from_end:
        return text[:max_chars]
    return text[-max_chars:]
