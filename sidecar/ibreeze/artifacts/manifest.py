"""Manifest structure for tracking artifact changes."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class ManifestEntry:
    """A single manifest entry tracking a file change."""

    def __init__(
        self,
        *,
        relative_path: str,
        action: str,  # "create", "modify", "delete"
        before_sha256: str | None = None,
        after_sha256: str | None = None,
        mode: int = 0o644,
        size_bytes: int = 0,
    ) -> None:
        self.relative_path = relative_path
        self.action = action
        self.before_sha256 = before_sha256
        self.after_sha256 = after_sha256
        self.mode = mode
        self.size_bytes = size_bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "action": self.action,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "mode": self.mode,
            "size_bytes": self.size_bytes,
        }


class Manifest:
    """Collection of manifest entries for an artifact."""

    def __init__(self) -> None:
        self.entries: list[ManifestEntry] = []

    def add_create(
        self,
        relative_path: str,
        after_sha256: str,
        size_bytes: int = 0,
        mode: int = 0o644,
    ) -> None:
        self.entries.append(
            ManifestEntry(
                relative_path=relative_path,
                action="create",
                after_sha256=after_sha256,
                size_bytes=size_bytes,
                mode=mode,
            )
        )

    def add_modify(
        self,
        relative_path: str,
        before_sha256: str,
        after_sha256: str,
        size_bytes: int = 0,
        mode: int = 0o644,
    ) -> None:
        self.entries.append(
            ManifestEntry(
                relative_path=relative_path,
                action="modify",
                before_sha256=before_sha256,
                after_sha256=after_sha256,
                size_bytes=size_bytes,
                mode=mode,
            )
        )

    def add_delete(self, relative_path: str, before_sha256: str) -> None:
        self.entries.append(
            ManifestEntry(
                relative_path=relative_path,
                action="delete",
                before_sha256=before_sha256,
            )
        )

    def to_json(self) -> str:
        return json.dumps([e.to_dict() for e in self.entries], indent=2)

    @classmethod
    def from_json(cls, data: str) -> Manifest:
        m = cls()
        for entry in json.loads(data):
            m.entries.append(ManifestEntry(**entry))
        return m

    def compute_manifest_hash(self) -> str:
        """Compute SHA-256 of the manifest content."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()
