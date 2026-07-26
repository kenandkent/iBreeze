"""Backup creation, retention, and restore service.

Uses SQLite Online Backup API to take consistent snapshots without
blocking concurrent readers. Writes are paused via WriteQueue barrier
during the snapshot window.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import tarfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import zstandard as zstd

from ibreeze.persistence.write_queue import WriteQueue

_SENSITIVE_FILES: frozenset[str] = frozenset({
    "secrets.json",
    "keys.db",
    ".env",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
})


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_table_stats(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        stats = {}
        for table in tables:
            cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
            stats[table] = cursor.fetchone()[0]
        return stats
    finally:
        conn.close()


def _collect_external_refs(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Collect external reference table rows for restore validation."""
    refs: dict[str, list[dict[str, Any]]] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        for row in cursor.fetchall():
            table = row[0]
            fk_cursor = conn.execute(f"PRAGMA foreign_key_list([{table}])")
            fk_rows = fk_cursor.fetchall()
            if not fk_rows:
                continue
            rows_cursor = conn.execute(f"SELECT rowid,* FROM [{table}]")
            cols = [desc[0] for desc in rows_cursor.description]
            table_rows = [dict(zip(cols, r)) for r in rows_cursor.fetchall()]
            refs[table] = table_rows
        return refs
    finally:
        conn.close()


def _sensitive_excluded(arcname: str) -> bool:
    for name in _SENSITIVE_FILES:
        if arcname.endswith(f"/{name}") or arcname == name:
            return True
    return False


def _archive_backup_package(
    db_snapshot: Path,
    cas_path: Path,
    output_path: Path,
    manifest: dict[str, Any],
) -> Path:
    archive_path = output_path.with_suffix(".tar.zst")
    with open(archive_path, "wb") as f:
        cctx = zstd.ZstdCompressor()
        with cctx.stream_writer(f) as writer:
            with tarfile.open(fileobj=writer, mode="w") as tar:
                tar.add(db_snapshot, arcname="data/profile.db")
                if cas_path.exists():
                    for root, _dirs, files in os.walk(cas_path):
                        for fname in files:
                            fpath = os.path.join(root, fname)
                            arcname = os.path.relpath(fpath, cas_path.parent)
                            if _sensitive_excluded(arcname):
                                continue
                            fsize = os.path.getsize(fpath)
                            MAX_CAS_FILE = 100 * 1024 * 1024
                            if fsize > MAX_CAS_FILE:
                                continue
                            fhash = _sha256_file(Path(fpath))
                            manifest["files"].append({
                                "path": arcname,
                                "sha256": fhash,
                                "size": fsize,
                            })
                            tar.add(fpath, arcname=arcname)
                manifest_bytes = json.dumps(manifest, indent=2).encode()
                manifest_info = tarfile.TarInfo(name="manifest.json")
                manifest_info.size = len(manifest_bytes)
                tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

    final_hash = _sha256_file(archive_path)
    manifest["archive_sha256"] = final_hash
    manifest["archive_size"] = os.path.getsize(archive_path)

    manifest_path = output_path.with_name(archive_path.name + ".manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, sort_keys=True, separators=(",", ":"))

    return archive_path


async def create_backup(
    db_path: Path,
    backup_dir: Path,
    *,
    backup_id: str | None = None,
    write_queue: WriteQueue | None = None,
    cas_path: Path | None = None,
) -> dict[str, Any]:
    """Create a backup using SQLite Online Backup API.

    Steps:
    1. Barrier the WriteQueue (wait for pending writes).
    2. Stream a consistent snapshot via sqlite3.backup().
    3. Compress snapshot + CAS objects into a tar.zst archive.
    4. Record manifest with SHA, refs, and exclude list.
    """
    bid = backup_id or _id()
    now = _now()
    backup_path = backup_dir / bid
    backup_path.mkdir(parents=True, exist_ok=True)

    if write_queue is not None:
        await write_queue.barrier()

    snapshot_path = backup_path / "ibreeze_snapshot.db"
    src_conn = sqlite3.connect(str(db_path))
    dst_conn = sqlite3.connect(str(snapshot_path))
    try:
        src_conn.backup(dst_conn, pages=1000)
    finally:
        dst_conn.close()
        src_conn.close()

    table_stats = _compute_table_stats(snapshot_path)
    db_hash = _sha256_file(snapshot_path)
    external_refs = _collect_external_refs(snapshot_path)

    manifest: dict[str, Any] = {
        "backup_id": bid,
        "created_at": now,
        "database_hash": db_hash,
        "table_stats": table_stats,
        "version": 1,
        "snapshot_method": "sqlite_online_backup",
        "external_refs": external_refs,
        "files": [],
        "sensitive_excluded": sorted(_SENSITIVE_FILES),
    }

    _cas = cas_path or Path("~/.ibreeze/cas").expanduser()
    archive_path = _archive_backup_package(snapshot_path, _cas, backup_path / "backup", manifest)

    os.remove(snapshot_path)

    return {
        "backup_id": bid,
        "archive_path": str(archive_path),
        "archive_sha256": manifest["archive_sha256"],
        "archive_size": manifest["archive_size"],
        "database_hash": db_hash,
        "table_stats": table_stats,
        "created_at": now,
        "file_count": len(manifest["files"]),
    }


async def restore_backup(
    backup_dir: Path,
    backup_id: str,
    target_db_path: Path,
    *,
    validate_manifest: bool = True,
) -> dict[str, Any]:
    """Restore from a backup archive with manifest validation."""
    backup_path = backup_dir / backup_id
    if not backup_path.exists():
        raise ValueError("BACKUP_NOT_FOUND")

    archives = list(backup_path.glob("backup*.tar.zst"))
    if not archives:
        raise ValueError("ARCHIVE_NOT_FOUND")
    archive_path = archives[0]

    manifest_path = list(backup_path.glob("*.manifest.json"))
    if not manifest_path:
        raise ValueError("MANIFEST_NOT_FOUND")

    with open(manifest_path[0]) as f:
        manifest = json.load(f)

    if validate_manifest:
        current_hash = _sha256_file(archive_path)
        expected = manifest.get("archive_sha256")
        if expected and current_hash != expected:
            raise ValueError("ARCHIVE_HASH_MISMATCH")

    staging_path = target_db_path.with_suffix(".staging")
    staging_path.parent.mkdir(parents=True, exist_ok=True)

    with open(archive_path, "rb") as f:
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(f) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as tar:
                db_found = False
                for member in tar:
                    if member.name == "data/profile.db":
                        db_found = True
                        src = tar.extractfile(member)
                        if src is None:
                            raise ValueError("DB_NOT_IN_ARCHIVE")
                        with open(staging_path, "wb") as out:
                            while True:
                                chunk = src.read(8192)
                                if not chunk:
                                    break
                                out.write(chunk)
                        break
                if not db_found:
                    raise ValueError("DB_NOT_IN_ARCHIVE")

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.rename(target_db_path)

    return {
        "backup_id": backup_id,
        "restored": True,
        "target": str(target_db_path),
        "database_hash": manifest.get("database_hash"),
    }


async def list_backups(backup_dir: Path) -> list[dict[str, Any]]:
    backups = []
    if not backup_dir.exists():
        return backups

    for entry in sorted(backup_dir.iterdir()):
        if not entry.is_dir():
            continue
        manifests = list(entry.glob("*.manifest.json"))
        if manifests:
            with open(manifests[0]) as f:
                manifest = json.load(f)
            backups.append(manifest)

    return backups


async def apply_retention_policy(
    backup_dir: Path,
    *,
    daily_retention: int = 7,
    weekly_retention: int = 4,
) -> dict[str, Any]:
    backups = await list_backups(backup_dir)
    if not backups:
        return {"deleted": 0, "daily_count": 0, "weekly_count": 0}

    now = datetime.now(UTC)
    daily_cutoff = now - timedelta(days=daily_retention)
    weekly_cutoff = now - timedelta(weeks=weekly_retention)

    daily_backups: list[dict[str, Any]] = []
    weekly_backups: list[dict[str, Any]] = []
    to_delete: list[dict[str, Any]] = []

    for backup in backups:
        created_at = datetime.fromisoformat(backup["created_at"].replace("Z", "+00:00"))
        if created_at >= daily_cutoff:
            daily_backups.append(backup)
        elif created_at >= weekly_cutoff:
            weekly_backups.append(backup)
        else:
            to_delete.append(backup)

    deleted = 0
    for backup in to_delete:
        backup_path = backup_dir / backup["backup_id"]
        if backup_path.exists():
            import shutil
            shutil.rmtree(backup_path)
            deleted += 1

    return {
        "deleted": deleted,
        "daily_count": len(daily_backups),
        "weekly_count": len(weekly_backups),
    }


async def delete_backup(backup_dir: Path, backup_id: str) -> dict[str, Any]:
    backup_path = backup_dir / backup_id
    if not backup_path.exists():
        raise ValueError("BACKUP_NOT_FOUND")

    import shutil
    shutil.rmtree(backup_path)
    return {"backup_id": backup_id, "deleted": True}
