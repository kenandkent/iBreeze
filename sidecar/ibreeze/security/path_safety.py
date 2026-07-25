"""Path traversal detection and safe path resolution."""

from __future__ import annotations

import time
from pathlib import Path


class PathViolationError(ValueError):
    pass


def resolve_safe(base_dir: str, requested_path: str) -> Path:
    """Resolve a path relative to base_dir, rejecting traversal."""
    base = Path(base_dir).resolve()
    target = (base / requested_path).resolve()
    if not str(target).startswith(str(base) + "/") and target != base:
        raise PathViolationError(f"Path traversal detected: {requested_path}")
    return target


def validate_no_traversal(path: str) -> bool:
    """Check if path contains traversal components."""
    return ".." not in path and not path.startswith("/")


def create_write_approval(
    normalized_path: str,
    content_hash: str,
    ttl_seconds: int = 3600,
) -> dict[str, object]:
    """Create a time-limited write approval for external writes."""
    import secrets

    token = secrets.token_hex(32)
    expires_at = time.time() + ttl_seconds
    return {
        "token": token,
        "normalized_path": normalized_path,
        "content_hash": content_hash,
        "expires_at": expires_at,
    }


def verify_write_approval(
    approval: dict[str, object],
    normalized_path: str,
    content_hash: str,
) -> bool:
    """Verify a write approval is valid and not expired."""
    if time.time() > float(approval["expires_at"]):  # type: ignore[arg-type]
        return False
    return (
        approval["normalized_path"] == normalized_path
        and approval["content_hash"] == content_hash
    )
