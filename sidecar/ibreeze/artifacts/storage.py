"""Content-addressable storage for artifacts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any


class ArtifactStorage:
    """Content-addressable storage for artifacts."""

    def __init__(self, base_path: str | None = None) -> None:
        self._base_path = base_path or os.path.expanduser("~/.ibreeze/artifacts")
        Path(self._base_path).mkdir(parents=True, exist_ok=True)

    def _cas_path(self, sha256: str) -> str:
        """Get CAS path: objects/sha256/{prefix}/{sha256}"""
        prefix = sha256[:2]
        return os.path.join(self._base_path, "objects", "sha256", prefix, sha256)

    def write(self, content: bytes) -> dict[str, Any]:
        """Write content to CAS with atomic rename.

        Flow: temp file → fsync → SHA-256 → atomic rename → fsync
        """
        sha256 = hashlib.sha256(content).hexdigest()
        cas_path = self._cas_path(sha256)

        if os.path.exists(cas_path):
            return {"sha256": sha256, "path": cas_path, "existed": True}

        parent_dir = os.path.dirname(cas_path)
        Path(parent_dir).mkdir(parents=True, exist_ok=True)

        temp_fd, temp_path = tempfile.mkstemp(dir=parent_dir)
        try:
            os.write(temp_fd, content)
            os.fsync(temp_fd)
            os.close(temp_fd)
            os.rename(temp_path, cas_path)
            dir_fd = os.open(parent_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            try:
                os.close(temp_fd)
            except OSError:
                pass
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        return {"sha256": sha256, "path": cas_path, "existed": False}

    def read(self, sha256: str) -> bytes | None:
        """Read content from CAS by SHA-256 hash."""
        cas_path = self._cas_path(sha256)
        if not os.path.exists(cas_path):
            return None
        with open(cas_path, "rb") as f:
            return f.read()

    def exists(self, sha256: str) -> bool:
        """Check if content exists in CAS."""
        return os.path.exists(self._cas_path(sha256))

    def compute_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()


_storage: ArtifactStorage | None = None


def get_storage() -> ArtifactStorage:
    """Get the singleton ArtifactStorage instance."""
    global _storage
    if _storage is None:
        _storage = ArtifactStorage()
    return _storage
