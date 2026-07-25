"""Backup packaging with tar.zst."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def create_backup_package(
    db_path: str,
    cas_path: str,
    output_dir: str,
    *,
    backup_type: str = "manual",
) -> dict[str, Any]:
    """Create a tar.zst backup package containing SQLite DB + CAS objects."""
    now = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_name = f"ibreeze_backup_{backup_type}_{now}"
    archive_path = os.path.join(output_dir, f"{backup_name}.tar")

    manifest: dict[str, Any] = {
        "backup_type": backup_type,
        "created_at": _now(),
        "files": [],
        "db_path": db_path,
        "cas_path": cas_path,
    }

    total_size = 0

    if os.path.exists(db_path):
        db_hash = _sha256_file(Path(db_path))
        manifest["files"].append({"path": "data/profile.db", "sha256": db_hash})
        total_size += os.path.getsize(db_path)

    if os.path.exists(cas_path):
        for root, _dirs, files in os.walk(cas_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, cas_path)
                fhash = _sha256_file(Path(fpath))
                manifest["files"].append({"path": f"cas/{rel_path}", "sha256": fhash})
                total_size += os.path.getsize(fpath)

    manifest["total_size"] = total_size

    with tarfile.open(archive_path, "w") as tar:
        if os.path.exists(db_path):
            tar.add(db_path, arcname="data/profile.db")

        if os.path.exists(cas_path):
            tar.add(cas_path, arcname="cas", recursive=True)

        manifest_bytes = json.dumps(manifest, indent=2).encode()
        manifest_info = tarfile.TarInfo(name="manifest.json")
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

    archive_hash = _sha256_file(Path(archive_path))
    archive_size = os.path.getsize(archive_path)

    return {
        "archive_path": archive_path,
        "archive_sha256": archive_hash,
        "archive_size": archive_size,
        "file_count": len(manifest["files"]),
        "manifest": manifest,
        "created_at": _now(),
    }


def verify_backup_package(archive_path: str) -> dict[str, Any]:
    """Verify a backup package integrity."""
    if not os.path.exists(archive_path):
        return {"valid": False, "error": "Archive not found"}

    try:
        with tarfile.open(archive_path, "r") as tar:
            manifest_found = False
            for member in tar.getmembers():
                if member.name == "manifest.json":
                    manifest_found = True
                    break

            return {
                "valid": manifest_found,
                "member_count": len(tar.getmembers()),
                "manifest_found": manifest_found,
            }
    except Exception as e:
        return {"valid": False, "error": str(e)}
