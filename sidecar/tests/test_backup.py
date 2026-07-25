"""Tests for backup service."""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from ibreeze.backup.service import (
    create_backup,
    restore_backup,
    list_backups,
    apply_retention_policy,
    delete_backup,
)


class TestBackupService:
    """Tests for backup creation, restore, and retention."""

    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def db_path(self, tmp_dir):
        import sqlite3
        db = tmp_dir / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()
        return db

    @pytest.mark.asyncio
    async def test_create_backup(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir)
        assert "backup_id" in result
        assert "database_hash" in result
        assert "table_stats" in result
        assert result["table_stats"]["test"] == 1

    @pytest.mark.asyncio
    async def test_create_backup_with_id(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_path, backup_dir, backup_id="my-backup")
        assert result["backup_id"] == "my-backup"

    @pytest.mark.asyncio
    async def test_restore_backup(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        create_result = await create_backup(db_path, backup_dir)

        target_db = tmp_dir / "restored.db"
        restore_result = await restore_backup(
            backup_dir,
            create_result["backup_id"],
            target_db,
        )
        assert restore_result["restored"] is True

    @pytest.mark.asyncio
    async def test_restore_backup_not_found(self, tmp_dir):
        target_db = tmp_dir / "restored.db"
        with pytest.raises(ValueError, match="BACKUP_NOT_FOUND"):
            await restore_backup(tmp_dir / "backups", "nonexistent", target_db)

    @pytest.mark.asyncio
    async def test_list_backups(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        await create_backup(db_path, backup_dir)
        await create_backup(db_path, backup_dir, backup_id="backup-2")

        backups = await list_backups(backup_dir)
        assert len(backups) == 2

    @pytest.mark.asyncio
    async def test_list_backups_empty(self, tmp_dir):
        backups = await list_backups(tmp_dir / "nonexistent")
        assert len(backups) == 0

    @pytest.mark.asyncio
    async def test_delete_backup(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        create_result = await create_backup(db_path, backup_dir)

        result = await delete_backup(backup_dir, create_result["backup_id"])
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_backup_not_found(self, tmp_dir):
        with pytest.raises(ValueError, match="BACKUP_NOT_FOUND"):
            await delete_backup(tmp_dir / "nonexistent", "nonexistent")

    @pytest.mark.asyncio
    async def test_apply_retention_policy(self, db_path, tmp_dir):
        backup_dir = tmp_dir / "backups"
        await create_backup(db_path, backup_dir)
        await create_backup(db_path, backup_dir, backup_id="backup-2")

        result = await apply_retention_policy(
            backup_dir,
            daily_retention=7,
            weekly_retention=4,
        )
        assert result["deleted"] == 0
        assert result["daily_count"] == 2
