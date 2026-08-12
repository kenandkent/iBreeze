"""Bounded, read-only tools exposed to the API Model Agent Loop.

Tool execution stays in the Sidecar, but every path is resolved against the
immutable workspace snapshot.  Mutating operations are intentionally not
implemented as direct tools; they must go through the approval/receipt path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_LIST_ENTRIES = 1000
MAX_SEARCH_RESULTS = 100


@dataclass(frozen=True, slots=True)
class ModelToolContext:
    workspace_root: Path
    purpose: str


def _relative_arg(arguments: dict[str, object], name: str = "path") -> str:
    value = arguments.get(name, arguments.get("relative_path", ""))
    if not isinstance(value, str) or not value.strip():
        raise ValueError("TOOL_PATH_REQUIRED")
    return value


def _resolve_read_path(root: Path, raw: str) -> Path:
    root = root.resolve(strict=True)
    candidate = Path(raw)
    if not candidate.is_absolute() and any(part == ".." for part in candidate.parts):
        raise ValueError("TOOL_PATH_OUTSIDE_WORKSPACE")
    lexical = candidate if candidate.is_absolute() else root / candidate
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ValueError("TOOL_PATH_OUTSIDE_WORKSPACE") from exc
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise ValueError("TOOL_SYMLINK_NOT_ALLOWED")
    resolved = lexical.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("TOOL_PATH_OUTSIDE_WORKSPACE")
    return resolved


def _contains_symlink(root: Path, path: Path) -> bool:
    """Return true when any workspace-relative component is a symlink."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            return True
    return False


def _bounded_limit(arguments: dict[str, object], key: str, default: int, maximum: int) -> int:
    value = arguments.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("TOOL_LIMIT_INVALID")
    return min(value, maximum)


async def read_file(context: ModelToolContext, arguments: dict[str, object]) -> dict[str, object]:
    path = _resolve_read_path(context.workspace_root, _relative_arg(arguments))
    if not path.is_file():
        raise ValueError("TOOL_FILE_REQUIRED")
    offset = arguments.get("offset", 0)
    length = arguments.get("length", MAX_FILE_BYTES)
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
        or not isinstance(length, int)
        or isinstance(length, bool)
        or length < 1
        or length > MAX_FILE_BYTES
    ):
        raise ValueError("TOOL_RANGE_INVALID")
    if offset > path.stat().st_size:
        raise ValueError("TOOL_RANGE_INVALID")
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(length)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("TOOL_FILE_TOO_LARGE")
    return {
        "path": str(path.relative_to(context.workspace_root)),
        "content": data.decode("utf-8", errors="replace"),
        "offset": offset,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


async def list_files(context: ModelToolContext, arguments: dict[str, object]) -> dict[str, object]:
    raw = arguments.get("path", arguments.get("relative_path", "."))
    if not isinstance(raw, str):
        raise ValueError("TOOL_PATH_INVALID")
    directory = _resolve_read_path(context.workspace_root, raw)
    if not directory.is_dir():
        raise ValueError("TOOL_DIRECTORY_REQUIRED")
    pattern = arguments.get("pattern", "*")
    if not isinstance(pattern, str) or not pattern or ".." in pattern:
        raise ValueError("TOOL_PATTERN_INVALID")
    limit = _bounded_limit(arguments, "limit", 200, MAX_LIST_ENTRIES)
    items: list[dict[str, object]] = []
    root = context.workspace_root.resolve(strict=True)
    for path in sorted(directory.rglob(pattern)):
        if _contains_symlink(root, path) or not path.is_file():
            continue
        items.append(
            {
                "path": str(path.relative_to(context.workspace_root)),
                "size": path.stat().st_size,
            }
        )
        if len(items) >= limit:
            break
    return {"items": items, "truncated": len(items) >= limit}


async def search_text(context: ModelToolContext, arguments: dict[str, object]) -> dict[str, object]:
    query = arguments.get("query")
    if not isinstance(query, str) or not query or len(query) > 256:
        raise ValueError("TOOL_QUERY_INVALID")
    raw = arguments.get("path", arguments.get("relative_path", "."))
    if not isinstance(raw, str):
        raise ValueError("TOOL_PATH_INVALID")
    directory = _resolve_read_path(context.workspace_root, raw)
    if not directory.is_dir():
        raise ValueError("TOOL_DIRECTORY_REQUIRED")
    max_results = _bounded_limit(arguments, "max_results", 50, MAX_SEARCH_RESULTS)
    results: list[dict[str, object]] = []
    root = context.workspace_root.resolve(strict=True)
    for path in sorted(directory.rglob("*")):
        if _contains_symlink(root, path) or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            if query in line:
                results.append(
                    {
                        "path": str(path.relative_to(context.workspace_root)),
                        "line": line_number,
                        "text": line[:4096],
                    }
                )
                if len(results) >= max_results:
                    return {"items": results, "truncated": True}
    return {"items": results, "truncated": False}


def build_model_tools(context: ModelToolContext) -> dict[str, Any]:
    """Return the fixed read-only tool registry for one run."""

    return {
        "read_file": lambda arguments: read_file(context, arguments),
        "list_files": lambda arguments: list_files(context, arguments),
        "search_text": lambda arguments: search_text(context, arguments),
    }
