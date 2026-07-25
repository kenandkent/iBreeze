"""Diff generation for text artifacts."""

from __future__ import annotations

import difflib
from typing import Any

MAX_DIFF_SIZE = 5 * 1024 * 1024  # 5 MiB


def generate_text_diff(
    old_content: str,
    new_content: str,
    *,
    filename: str = "",
    context_lines: int = 3,
) -> dict[str, Any]:
    """Generate a unified diff between two text contents."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=context_lines,
    )

    diff_text = "".join(diff)

    return {
        "diff": diff_text,
        "line_count": len(diff_text.splitlines()),
        "size_bytes": len(diff_text.encode()),
        "needs_separate_artifact": len(diff_text.encode()) > MAX_DIFF_SIZE,
    }


def is_text_content(content: bytes) -> bool:
    """Check if content is text (not binary)."""
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def should_generate_diff(content: bytes) -> bool:
    """Check if we should generate a diff for this content."""
    return is_text_content(content) and len(content) <= MAX_DIFF_SIZE
