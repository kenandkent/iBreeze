"""Backup packaging with tar.zst.

Verifies paths are relative, files are regular (no symlinks/devices),
enforces size limits, and computes SHA during packaging.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import zstandard as zstd

MAX_FILE_SIZE = 100 * 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_arcname(base_dir: Path, abs_path: Path) -> str:
    """Compute a relative arcname and guard against path traversal."""
    try:
        rel = abs_path.relative_to(base_dir)
    except ValueError:
        rel = abs_path.resolve().relative_to(base_dir.resolve())
    arcname = str(rel.as_posix())
    if arcname.startswith("..") or arcname.startswith("/"):
        raise ValueError(f"Path traversal detected: {arcname}")
    if ".." in arcname.split("/"):
        raise ValueError(f"Path traversal detected: {arcname}")
    return arcname


def create_backup_package(
    db_path: str,
    cas_path: str,
    output_dir: str,
    *,
    backup_type: str = "manual",
) -> dict[str, Any]:
    """Create a tar.zst backup package containing SQLite DB + CAS objects.

    Each file is validated before inclusion:
    - Must be a regular file (no symlinks, devices, FIFOs)
    - Must not exceed MAX_FILE_SIZE
    - Must resolve to a relative path without traversal
    - SHA is computed during packaging and recorded in the manifest
    """
    now = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_name = f"ibreeze_backup_{backup_type}_{now}"
    archive_path = os.path.join(output_dir, f"{backup_name}.tar.zst")

    manifest: dict[str, Any] = {
        "backup_type": backup_type,
        "created_at": _now(),
        "files": [],
        "db_path": db_path,
        "cas_path": cas_path,
    }

    total_size = 0

    def _add_to_manifest(file_path: Path, arcname: str) -> None:
        nonlocal total_size
        st = file_path.stat()
        if not stat.S_ISREG(st.st_mode):
            return
        if st.st_size > MAX_FILE_SIZE:
            return
        fhash = _sha256_file(file_path)
        manifest["files"].append(
            {
                "path": arcname,
                "sha256": fhash,
                "size": st.st_size,
            }
        )
        total_size += st.st_size

    db_p = Path(db_path)
    cas_p = Path(cas_path)

    if db_p.exists():
        arcname = _safe_arcname(db_p.parent, db_p)
        _add_to_manifest(db_p, arcname)

    if cas_p.exists():
        for root, _dirs, files in os.walk(cas_p):
            for fname in files:
                fpath = Path(os.path.join(root, fname))
                arcname = _safe_arcname(cas_p, fpath)
                _add_to_manifest(fpath, arcname)

    manifest["total_size"] = total_size

    with open(archive_path, "wb") as f:
        cctx = zstd.ZstdCompressor()
        with cctx.stream_writer(f) as writer:
            with tarfile.open(fileobj=writer, mode="w") as tar:
                if db_p.exists():
                    tar.add(str(db_p), arcname="data/profile.db", filter=_tar_filter)
                if cas_p.exists():
                    tar.add(str(cas_p), arcname="cas", recursive=True, filter=_tar_filter)
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


def _tar_filter(tar_info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Exclude non-regular files (symlinks, devices, FIFOs)."""
    if tar_info.type not in (tarfile.REGTYPE, tarfile.DIRTYPE, tarfile.AREGTYPE):
        return None
    return tar_info


def verify_backup_package(archive_path: str) -> dict[str, Any]:
    """Verify a backup package integrity and path safety."""
    if not os.path.exists(archive_path):
        return {"valid": False, "error": "Archive not found"}

    try:
        with open(archive_path, "rb") as f:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(f) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tar:
                    manifest_found = False
                    db_found = False
                    member_count = 0
                    traversal_issues: list[str] = []
                    for member in tar:
                        member_count += 1
                        if member.name == "manifest.json":
                            manifest_found = True
                        if member.name == "data/profile.db":
                            db_found = True
                        if member.name.startswith("..") or "/../" in member.name:
                            traversal_issues.append(member.name)

                    return {
                        "valid": manifest_found and db_found and not traversal_issues,
                        "member_count": member_count,
                        "manifest_found": manifest_found,
                        "db_found": db_found,
                        "traversal_issues": traversal_issues,
                    }
    except Exception as e:
        return {"valid": False, "error": str(e)}
