"""Document chunking service — Markdown, code and generic text."""

from __future__ import annotations

from typing import Any


def chunk_markdown(text: str, max_tokens: int = 800) -> list[dict[str, Any]]:
    """Chunk markdown text into segments of *max_tokens* tokens.

    Splitting strategy:
    - Split on paragraph breaks (``\\n\\n``)
    - Each paragraph is treated as a potential chunk boundary
    - Rough token estimate: 1 token ~ 4 chars (Chinese) / 5 chars (English)
    """
    chunks: list[dict[str, Any]] = []
    current_chunk = ""
    current_tokens = 0

    paragraphs = text.split("\n\n")
    for para in paragraphs:
        para_tokens = max(len(para) // 4, 1)

        if current_tokens + para_tokens > max_tokens and current_chunk:
            chunks.append({"text": current_chunk.strip(), "token_count": current_tokens})
            current_chunk = para
            current_tokens = para_tokens
        else:
            current_chunk += ("\n\n" if current_chunk else "") + para
            current_tokens += para_tokens

    if current_chunk.strip():
        chunks.append({"text": current_chunk.strip(), "token_count": current_tokens})

    return chunks


def chunk_code(text: str, language: str = "", max_tokens: int = 1200) -> list[dict[str, Any]]:
    """Chunk code text into logical segments.

    Splitting strategy:
    - Split on function/class boundaries
    - Keep imports and top-level definitions together
    """
    chunks: list[dict[str, Any]] = []
    current_chunk = ""
    current_tokens = 0

    lines = text.split("\n")
    for line in lines:
        line_tokens = max(len(line) // 5, 1)

        is_boundary = any(line.strip().startswith(kw) for kw in ["def ", "class ", "async def ", "function ", "export "])

        if is_boundary and current_tokens + line_tokens > max_tokens and current_chunk:
            chunks.append({"text": current_chunk.strip(), "token_count": current_tokens, "language": language})
            current_chunk = line
            current_tokens = line_tokens
        else:
            current_chunk += ("\n" if current_chunk else "") + line
            current_tokens += line_tokens

    if current_chunk.strip():
        chunks.append({"text": current_chunk.strip(), "token_count": current_tokens, "language": language})

    return chunks


def chunk_text(text: str, max_tokens: int = 800) -> list[dict[str, Any]]:
    """Generic text chunking — delegates to :func:`chunk_markdown`."""
    return chunk_markdown(text, max_tokens)
