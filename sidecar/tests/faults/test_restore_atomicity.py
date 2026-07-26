"""Fault-tolerance tests for restore atomicity (R09).

- FLT-RST-001: Restore does not corrupt original on failure
- FLT-RST-002: Partial archive extraction is rejected
- FLT-RST-003: Restore validates migration chain completeness
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
import tempfile
from pathlib import Path

import pytest

from ibreeze.backup.validator import restore_from_backup, validate_backup_database


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _create_valid_backup_archive(archive_path: str, db_path: str) -> None:
    """Create a minimal valid tar.gz (not zst) archive for validation."""
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(db_path, arcname="data/profile.db")
        manifest = json.dumps({"test": True}).encode()
        tinfo = tarfile.TarInfo(name="manifest.json")
        tinfo.size = len(manifest)
        tar.addfile(tinfo, io.BytesIO(manifest))


@pytest.mark.asyncio
class TestRestoreAtomicOnFailure:
    """FLT-RST-001: Restore leaves original intact on failure."""

    async def test_failure_does_not_remove_original(self, tmp_dir):
        original_db = os.path.join(tmp_dir, "original.db")
        conn = sqlite3.connect(original_db)
        conn.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO data VALUES (1, 'preserve me')")
        conn.commit()
        conn.close()

        bad_archive = os.path.join(tmp_dir, "bad_archive.tar.gz")
        conn2 = sqlite3.connect(os.path.join(tmp_dir, "bad.db"))
        conn2.execute("CREATE TABLE empty (id INTEGER PRIMARY KEY)")
        conn2.commit()
        conn2.close()

        with tarfile.open(bad_archive, "w:gz") as tar:
            manifest = json.dumps({"test": True}).encode()
            tinfo = tarfile.TarInfo(name="manifest.json")
            tinfo.size = len(manifest)
            tar.addfile(tinfo, io.BytesIO(manifest))

        await restore_from_backup(
            original_db,
            bad_archive,
            staging_dir=tmp_dir,
        )

        conn3 = sqlite3.connect(original_db)
        cursor = conn3.execute("SELECT value FROM data WHERE id=1")
        row = cursor.fetchone()
        conn3.close()
        assert row is not None
        assert row[0] == "preserve me"


@pytest.mark.asyncio
class TestPartialArchiveRejection:
    """FLT-RST-002: Partial archive extraction is rejected."""

    async def test_missing_db_in_archive_rejected(self, tmp_dir):
        target_db = os.path.join(tmp_dir, "target.db")
        archive = os.path.join(tmp_dir, "no_db.tar.gz")

        with tarfile.open(archive, "w:gz") as tar:
            manifest = json.dumps({"test": True}).encode()
            tinfo = tarfile.TarInfo(name="manifest.json")
            tinfo.size = len(manifest)
            tar.addfile(tinfo, io.BytesIO(manifest))

        result = await restore_from_backup(target_db, archive, staging_dir=tmp_dir)
        assert result["success"] is False


@pytest.mark.asyncio
class TestMigrationChainValidation:
    """FLT-RST-003: Restore validates migration chain completeness."""

    async def test_restore_without_migrations_rejected(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "bare.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE companies (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO companies VALUES ('c1')")
        conn.commit()
        conn.close()

        archive = os.path.join(tmp_dir, "bare_backup.tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(db_path, arcname="data/profile.db")
            manifest = json.dumps({"test": True}).encode()
            tinfo = tarfile.TarInfo(name="manifest.json")
            tinfo.size = len(manifest)
            tar.addfile(tinfo, io.BytesIO(manifest))

        target = os.path.join(tmp_dir, "restored.db")
        result = await restore_from_backup(target, archive, staging_dir=tmp_dir)
        assert result["success"] is False
