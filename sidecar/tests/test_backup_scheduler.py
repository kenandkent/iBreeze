from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from ibreeze.backup.scheduler import (
    apply_retention_policy,
    should_run_daily_backup,
    should_run_pre_upgrade_backup,
    trigger_daily_backup,
)


@pytest.mark.asyncio
class TestShouldRunDailyBackup:
    async def test_returns_true_when_no_records(self):
        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone.return_value = None
        db.execute.return_value = cursor
        result = await should_run_daily_backup(db)
        assert result is True

    async def test_returns_true_when_over_24_hours(self):
        db = AsyncMock()
        cursor = AsyncMock()
        old_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
        cursor.fetchone.return_value = {"created_at": old_time}
        db.execute.return_value = cursor
        result = await should_run_daily_backup(db)
        assert result is True

    async def test_returns_false_when_under_24_hours(self):
        db = AsyncMock()
        cursor = AsyncMock()
        recent_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        cursor.fetchone.return_value = {"created_at": recent_time}
        db.execute.return_value = cursor
        result = await should_run_daily_backup(db)
        assert result is False


@pytest.mark.asyncio
class TestShouldRunPreUpgradeBackup:
    async def test_always_returns_true(self):
        result = await should_run_pre_upgrade_backup(AsyncMock())
        assert result is True


@pytest.mark.asyncio
class TestTriggerDailyBackup:
    async def test_returns_none_when_not_needed(self):
        db = AsyncMock()
        cursor = AsyncMock()
        recent_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        cursor.fetchone.return_value = {"created_at": recent_time}
        db.execute.return_value = cursor
        result = await trigger_daily_backup(db, "/tmp")
        assert result is None


@pytest.mark.asyncio
class TestApplyRetentionPolicy:
    async def test_deleted_returns_zero_when_no_backups(self):
        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = []
        db.execute.return_value = cursor
        result = await apply_retention_policy(db)
        assert result == {"deleted": 0}

    async def test_deletes_old_daily_backups(self):
        db = AsyncMock()
        old_date = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {"id": "1", "backup_type": "daily", "created_at": old_date},
        ]
        db.execute.return_value = cursor
        result = await apply_retention_policy(db)
        assert result["deleted"] == 1

    async def test_keeps_recent_daily_backups(self):
        db = AsyncMock()
        recent_date = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {"id": "1", "backup_type": "daily", "created_at": recent_date},
        ]
        db.execute.return_value = cursor
        result = await apply_retention_policy(db)
        assert result["deleted"] == 0

    async def test_skips_manual_backups(self):
        db = AsyncMock()
        old_date = (datetime.now(UTC) - timedelta(days=100)).isoformat().replace("+00:00", "Z")
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {"id": "1", "backup_type": "manual", "created_at": old_date},
        ]
        db.execute.return_value = cursor
        result = await apply_retention_policy(db)
        assert result["deleted"] == 0

    async def test_commits_when_deleted(self):
        db = AsyncMock()
        old_date = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {"id": "1", "backup_type": "daily", "created_at": old_date},
        ]
        db.execute.return_value = cursor
        result = await apply_retention_policy(db)
        assert result["deleted"] == 1
        db.commit.assert_awaited_once()
