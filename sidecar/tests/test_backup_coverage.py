"""Coverage tests for backup scheduler, validator, packager, and service.

Targets the uncovered lines:
- scheduler.py: _now (11), trigger_daily_backup full path (37-58), weekly
  retention branch (97)
- validator.py: index-corruption loop (131-135, 138), restore arc 249->263
- packager.py: path traversal guards (44, 46), non-regular/oversize skip (83,
  85), verify exception (175-176)
- service.py: MANIFEST_NOT_FOUND (228), restore db-not-found arcs (247->260,
  248->247, 261), symlink extractfile None (252), list_backups skips (281,
  283->279), retention weekly/to_delete branches (313-316, 320-325)
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import zstandard as zstd

from ibreeze.backup.packager import _safe_arcname, create_backup_package, verify_backup_package
from ibreeze.backup.scheduler import (
    _now as scheduler_now,
)
from ibreeze.backup.scheduler import (
    apply_retention_policy as scheduler_retention,
)
from ibreeze.backup.scheduler import (
    trigger_daily_backup,
)
from ibreeze.backup.service import (
    apply_retention_policy as service_retention,
)
from ibreeze.backup.service import (
    list_backups,
    restore_backup,
)
from ibreeze.backup.validator import restore_from_backup, validate_backup_database


def _zstd_tar(members: list[tuple[str, bytes | None, str | None]], out_path: Path) -> Path:
    """Write a zstd-compressed tar. Each member is (name, data, linkname);
    linkname set means a symlink member."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data, linkname in members:
            info = tarfile.TarInfo(name)
            if linkname is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
                tar.addfile(info)
            else:
                assert data is not None
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    cctx = zstd.ZstdCompressor()
    out_path.write_bytes(cctx.compress(buf.getvalue()))
    return out_path


def _iso(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


# ── scheduler.py ───────────────────────────────────────────────────────────


class TestSchedulerCoverage:
    def test_now_ends_with_z(self):
        assert scheduler_now().endswith("Z")

    @pytest.mark.asyncio
    async def test_trigger_daily_backup_full_path(self, tmp_path):
        """scheduler.py:37-58 — full happy path when a daily backup is due."""
        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)  # no last daily -> due
        db.execute = AsyncMock(return_value=cursor)

        result_pkg = {
            "archive_path": "/tmp/out/ibreeze.tar.zst",
            "archive_sha256": "0" * 64,
            "archive_size": 10,
            "manifest": {"files": []},
            "created_at": "2026-01-01T00:00:00Z",
        }
        with (
            patch("ibreeze.backup.packager.create_backup_package", return_value=result_pkg),
            patch(
                "ibreeze.backup.records.create_backup_record",
                AsyncMock(return_value={"id": "bk-1"}),
            ),
            patch("ibreeze.backup.records.complete_backup_record", AsyncMock()),
        ):
            result = await trigger_daily_backup(db, str(tmp_path))

        assert result == {
            "backup_id": "bk-1",
            "archive_path": "/tmp/out/ibreeze.tar.zst",
            "created_at": "2026-01-01T00:00:00Z",
        }

    @pytest.mark.asyncio
    async def test_weekly_retention_deletes(self):
        """scheduler.py:97 — old weekly backups are marked deleted."""
        db = AsyncMock()
        row = {"id": "bk-9", "backup_type": "weekly", "created_at": _iso(30)}
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[row])
        db.execute = AsyncMock(side_effect=[cursor, AsyncMock()])
        result = await scheduler_retention(db)
        assert result == {"deleted": 1}


# ── validator.py ───────────────────────────────────────────────────────────


class TestValidatorCoverage:
    @pytest.mark.asyncio
    async def test_index_corruption_detected(self, tmp_path):
        """validator.py:131-135,138 — DROP on an unquoted hyphenated index fails."""
        db_path = str(tmp_path / "backup.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE companies (id TEXT PRIMARY KEY)")
        conn.execute('CREATE INDEX "my-index" ON companies (id)')
        conn.commit()
        conn.close()

        result = await validate_backup_database(db_path)
        assert any("Index issues" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_restore_skips_migrations_when_key_absent(self, tmp_path):
        """validator.py:249->263 — restore continues when db_validation lacks migrations."""
        archive = _zstd_tar(
            [
                ("manifest.json", b"{}", None),
                ("data/profile.db", b"dbfile", None),
            ],
            tmp_path / "backup.tar.zst",
        )
        with patch(
            "ibreeze.backup.validator.validate_backup_database",
            AsyncMock(return_value={"valid": True}),
        ):
            result = await restore_from_backup(
                str(tmp_path / "restored.db"),
                str(archive),
                staging_dir=str(tmp_path / "staging"),
            )
        assert result["success"] is True


# ── packager.py ────────────────────────────────────────────────────────────


class TestPackagerCoverage:
    def test_traversal_dotdot_prefix(self):
        """packager.py:44 — leading '..' arcname is rejected."""
        with pytest.raises(ValueError, match="traversal"):
            _safe_arcname(Path("/tmp/foo"), Path("/tmp/foo/../x"))

    def test_traversal_mid_dotdot(self):
        """packager.py:46 — '..' component in the middle is rejected."""
        with pytest.raises(ValueError, match="traversal"):
            _safe_arcname(Path("/tmp/foo"), Path("/tmp/foo/a/../b"))

    def test_fifo_and_oversize_excluded(self, tmp_path):
        """packager.py:83,85 — FIFOs and oversize files are skipped."""
        cas = tmp_path / "cas"
        cas.mkdir()
        (tmp_path / "out").mkdir()
        (cas / "big.bin").write_bytes(b"x" * 200)
        os.mkfifo(cas / "pipe")
        with patch("ibreeze.backup.packager.MAX_FILE_SIZE", 100):
            result = create_backup_package(
                str(tmp_path / "nope.db"),
                str(cas),
                str(tmp_path / "out"),
            )
        assert result["file_count"] == 0

    def test_verify_corrupt_archive(self, tmp_path):
        """packager.py:175-176 — non-zstd input returns an error dict."""
        bad = tmp_path / "bad.zst"
        bad.write_bytes(b"not a zstd stream")
        result = verify_backup_package(str(bad))
        assert result["valid"] is False
        assert "error" in result


# ── service.py ─────────────────────────────────────────────────────────────


class TestBackupServiceCoverage:
    @pytest.mark.asyncio
    async def test_restore_manifest_not_found(self, tmp_path):
        """service.py:228 — archive without manifest raises MANIFEST_NOT_FOUND."""
        bid_dir = tmp_path / "b1"
        bid_dir.mkdir(parents=True)
        (bid_dir / "backup.tar.zst").write_bytes(b"x")
        with pytest.raises(ValueError, match="MANIFEST_NOT_FOUND"):
            await restore_backup(tmp_path, "b1", tmp_path / "restored.db")

    @pytest.mark.asyncio
    async def test_restore_db_not_in_archive(self, tmp_path):
        """service.py:247->260,248->247,261 — archive without the db member."""
        bid_dir = tmp_path / "b1"
        bid_dir.mkdir(parents=True)
        _zstd_tar([("manifest.json", b"{}", None)], bid_dir / "backup.tar.zst")
        (bid_dir / "b1.manifest.json").write_text("{}")
        with pytest.raises(ValueError, match="DB_NOT_IN_ARCHIVE"):
            await restore_backup(tmp_path, "b1", tmp_path / "restored.db")

    @pytest.mark.asyncio
    async def test_restore_db_symlink_extract_none(self, tmp_path):
        """service.py:252 — extractfile returning None raises DB_NOT_IN_ARCHIVE.

        A stream-mode tar raises StreamError instead of returning None for
        symlinks, so force the None return to reach the guard.
        """
        bid_dir = tmp_path / "b1"
        bid_dir.mkdir(parents=True)
        _zstd_tar(
            [
                ("manifest.json", b"{}", None),
                ("data/profile.db", None, "/etc/passwd"),
            ],
            bid_dir / "backup.tar.zst",
        )
        (bid_dir / "b1.manifest.json").write_text("{}")

        real_extractfile = tarfile.TarFile.extractfile

        def fake_extractfile(self, member):
            if getattr(member, "name", "") == "data/profile.db":
                return None
            return real_extractfile(self, member)

        with patch.object(tarfile.TarFile, "extractfile", fake_extractfile):
            with pytest.raises(ValueError, match="DB_NOT_IN_ARCHIVE"):
                await restore_backup(tmp_path, "b1", tmp_path / "restored.db")

    @pytest.mark.asyncio
    async def test_list_backups_skips_files_and_empty_dirs(self, tmp_path):
        """service.py:281,283->279 — non-dirs and dirs without manifests skipped."""
        (tmp_path / "note.txt").write_text("x")
        (tmp_path / "d1").mkdir()
        d2 = tmp_path / "d2"
        d2.mkdir()
        (d2 / "d2.manifest.json").write_text(
            json.dumps({"backup_id": "d2", "created_at": "2026-01-01T00:00:00Z"})
        )
        result = await list_backups(tmp_path)
        assert [b["backup_id"] for b in result] == ["d2"]

    @pytest.mark.asyncio
    async def test_retention_weekly_and_delete(self, tmp_path):
        """service.py:313-316,320-325 — weekly bucket and to_delete deletion."""
        for bid, days in [("d1", 1), ("w1", 10), ("old1", 30)]:
            d = tmp_path / bid
            d.mkdir()
            (d / f"{bid}.manifest.json").write_text(
                json.dumps({"backup_id": bid, "created_at": _iso(days)})
            )
        result = await service_retention(tmp_path)
        assert result == {"deleted": 1, "daily_count": 1, "weekly_count": 1}
        assert not (tmp_path / "old1").exists()
