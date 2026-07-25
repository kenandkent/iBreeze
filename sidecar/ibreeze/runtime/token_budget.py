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
    model_id: str,
    *,
    system_prompt_tokens: int = 0,
    reserved_output_tokens: int = 4096,
) -> dict[str, int]:
    """Calculate token budget for a model."""
    total = _DEFAULT_LIMIT
    model_lower = model_id.lower()
    for prefix, limit in MODEL_LIMITS.items():
        if prefix in model_lower:
            total = limit
            break

    available = total - system_prompt_tokens - reserved_output_tokens
    return {
        "total_tokens": total,
        "system_prompt_tokens": system_prompt_tokens,
        "reserved_output_tokens": reserved_output_tokens,
        "available_tokens": max(available, 0),
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
