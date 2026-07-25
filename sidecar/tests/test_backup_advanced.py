"""Tests for backup advanced scenarios.

Covers BACK-002, BACK-003, BACK-004, BACK-005.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from ibreeze.backup.service import (
    apply_retention_policy,
    create_backup,
    delete_backup,
    list_backups,
    restore_backup,
)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_path(tmp_dir):
    db = tmp_dir / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO companies VALUES ('c1', '测试公司')")
    conn.execute("CREATE TABLE employees (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO employees VALUES ('e1', '员工一')")
    conn.commit()
    conn.close()
    return db


@pytest.mark.asyncio
class TestRetentionPolicy:
    """BACK-002: Old backups should be pruned by retention policy."""

    async def test_retention_no_old_backups(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        await create_backup(db_path, backup_dir, backup_id="backup-new")
        result = await apply_retention_policy(
            backup_dir, daily_retention=7, weekly_retention=4
        )
        assert result["deleted"] == 0
        assert result["daily_count"] == 1

    async def test_retention_keeps_weekly(self, db_path, tmp_dir):
        """BACK-002: Backups within weekly range are kept."""
        backup_dir = tmp_dir / "backups"
        await create_backup(db_path, backup_dir, backup_id="backup-1")
        await create_backup(db_path, backup_dir, backup_id="backup-2")
        result = await apply_retention_policy(
            backup_dir, daily_retention=7, weekly_retention=4
        )
        assert result["deleted"] == 0

    async def test_retention_empty_dir(self, tmp_dir):
        backup_dir = tmp_dir / "empty-backups"
        result = await apply_retention_policy(backup_dir)
        assert result["deleted"] == 0

    async def test_list_backups_returns_manifest(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        await create_backup(db_path, backup_dir, backup_id="manifest-test")
        backups = await list_backups(backup_dir)
        assert len(backups) == 1
        assert backups[0]["backup_id"] == "manifest-test"
        assert "database_hash" in backups[0]
        assert "table_stats" in backups[0]

    async def test_delete_specific_backup(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        await create_backup(db_path, backup_dir, backup_id="to-delete")
        await create_backup(db_path, backup_dir, backup_id="to-keep")
        await delete_backup(backup_dir, "to-delete")
        backups = await list_backups(backup_dir)
        assert len(backups) == 1
        assert backups[0]["backup_id"] == "to-keep"


@pytest.mark.asyncio
class TestRestoreValidation:
    """BACK-003: Restore should validate backup integrity."""

    async def test_restore_validates_manifest_hash(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir, backup_id="valid")
        target = tmp_dir / "restored.db"
        restore_result = await restore_backup(
            backup_dir, result["backup_id"], target, validate_manifest=True
        )
        assert restore_result["restored"] is True

    async def test_restore_not_found(self, tmp_dir):
        with pytest.raises(ValueError, match="BACKUP_NOT_FOUND"):
            await restore_backup(
                tmp_dir / "backups", "nonexistent", tmp_dir / "target.db"
            )

    async def test_restore_manifest_not_found(self, tmp_dir):
        backup_dir = tmp_dir / "backups"
        backup_dir.mkdir()
        (backup_dir / "no-manifest").mkdir()
        with pytest.raises(ValueError, match="MANIFEST_NOT_FOUND"):
            await restore_backup(
                backup_dir, "no-manifest", tmp_dir / "target.db"
            )

    async def test_restore_hash_mismatch(self, db_path, tmp_dir):
        """BACK-003: Restore rejects tampered backup."""
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir, backup_id="tamper")
        manifest_path = backup_dir / "tamper" / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        manifest["database_hash"] = "0" * 64
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)
        with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
            await restore_backup(
                backup_dir,
                "tamper",
                tmp_dir / "target.db",
                validate_manifest=True,
            )

    async def test_restore_without_validation(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir, backup_id="skip")
        target = tmp_dir / "restored.db"
        restore_result = await restore_backup(
            backup_dir, result["backup_id"], target, validate_manifest=False
        )
        assert restore_result["restored"] is True


@pytest.mark.asyncio
class TestAtomicRestoreSwitch:
    """BACK-004: Restore should be atomic (swap, not merge)."""

    async def test_restore_overwrites_target(self, db_path, tmp_dir):
        """BACK-004: Restore replaces the target file entirely."""
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir, backup_id="atomic")
        target = tmp_dir / "target.db"
        target.touch()
        restore_result = await restore_backup(
            backup_dir, result["backup_id"], target
        )
        assert restore_result["restored"] is True
        restored_path = Path(restore_result["target"])
        assert restored_path.exists()
        conn = sqlite3.connect(str(restored_path))
        cursor = conn.execute("SELECT name FROM companies WHERE id='c1'")
        row = cursor.fetchone()
        conn.close()
        assert row[0] == "测试公司"

    async def test_restore_creates_staging_and_renames(self, db_path, tmp_dir):
        """BACK-004: Restore uses staging file for atomicity."""
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir, backup_id="staging")
        target = tmp_dir / "target.db"
        await restore_backup(backup_dir, result["backup_id"], target)
        staging = target.with_suffix(".staging")
        assert not staging.exists()

    async def test_backup_preserves_all_tables(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir)
        assert "companies" in result["table_stats"]
        assert "employees" in result["table_stats"]
        assert result["table_stats"]["companies"] == 1
        assert result["table_stats"]["employees"] == 1


@pytest.mark.asyncio
class TestRestorePostConstraints:
    """BACK-005: Post-restore should enforce all constraints."""

    async def test_restored_db_is_usable(self, db_path, tmp_dir):
        """BACK-005: Restored database is fully functional."""
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir)
        target = tmp_dir / "restored.db"
        restore_result = await restore_backup(backup_dir, result["backup_id"], target)
        conn = sqlite3.connect(restore_result["target"])
        conn.execute("INSERT INTO companies VALUES ('c2', '新公司')")
        cursor = conn.execute("SELECT COUNT(*) FROM companies")
        assert cursor.fetchone()[0] == 2
        conn.close()

    async def test_restored_db_schema_integrity(self, db_path, tmp_dir):
        """BACK-005: Restored database has correct schema."""
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir)
        target = tmp_dir / "restored.db"
        restore_result = await restore_backup(backup_dir, result["backup_id"], target)
        conn = sqlite3.connect(restore_result["target"])
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "companies" in tables
        assert "employees" in tables

    async def test_multiple_restores_consistent(self, db_path, tmp_dir):
        """BACK-005: Multiple restores produce same result."""
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir, backup_id="repeat")
        for i in range(3):
            target = tmp_dir / f"restored-{i}.db"
            restore_result = await restore_backup(backup_dir, result["backup_id"], target)
            conn = sqlite3.connect(restore_result["target"])
            cursor = conn.execute("SELECT name FROM companies WHERE id='c1'")
            assert cursor.fetchone()[0] == "测试公司"
            conn.close()
