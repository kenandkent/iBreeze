"""Filesystem-backed development object store with traversal-safe object keys."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath


class ObjectStorage:
    """Development adapter for the S3 object-store contract."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = (base_path or Path("storage")).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def put_object(self, object_key: str, source: Path) -> Path:
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    def put_bytes(self, object_key: str, value: bytes) -> Path:
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_bytes(value)
        temporary.replace(destination)
        return destination

    def get_bytes(self, object_key: str) -> bytes | None:
        path = self.get_object_path(object_key)
        return path.read_bytes() if path is not None else None

    def copy_object(self, source_key: str, destination_key: str) -> Path:
        return self.put_object(destination_key, self._path(source_key))

    def get_object_path(self, object_key: str) -> Path | None:
        path = self._path(object_key)
        return path if path.is_file() else None

    def delete_object(self, object_key: str) -> bool:
        path = self._path(object_key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, object_key: str) -> Path:
        candidate = PurePosixPath(object_key)
        if (
            candidate.is_absolute()
            or not candidate.parts
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise ValueError("OBJECT_KEY_INVALID")
        path = self.base_path.joinpath(*candidate.parts).resolve()
        if not path.is_relative_to(self.base_path):
            raise ValueError("OBJECT_KEY_INVALID")
        return path
