from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ibreeze.backup.records import (
    complete_backup_record,
    create_backup_record,
    fail_backup_record,
    get_backup_record,
    list_backup_records,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.mark.asyncio
class TestBackupRecords:
    async def test_create_record(self, mock_db):
        cursor = AsyncMock()
        mock_db.execute.return_value = cursor
        result = await create_backup_record(
            mock_db,
            backup_type="manual",
            file_path="/tmp/test.tar.zst",
            sha256="abc123",
            file_size=1024,
            manifest={"key": "value"},
        )
        assert result["status"] == "creating"
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_complete_record(self, mock_db):
        cursor = AsyncMock()
        mock_db.execute.return_value = cursor
        result = await complete_backup_record(mock_db, "record-1")
        assert result["status"] == "completed"
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_fail_record(self, mock_db):
        cursor = AsyncMock()
        mock_db.execute.return_value = cursor
        result = await fail_backup_record(mock_db, "record-1", "BACKUP_ERROR")
        assert result["status"] == "failed"
        assert result["error_code"] == "BACKUP_ERROR"
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_list_records_empty(self, mock_db):
        cursor = AsyncMock()
        cursor.fetchall.return_value = []
        mock_db.execute.return_value = cursor
        result = await list_backup_records(mock_db)
        assert result == []

    async def test_list_records_with_rows(self, mock_db):
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {"id": "1", "status": "completed"},
            {"id": "2", "status": "creating"},
        ]
        mock_db.execute.return_value = cursor
        result = await list_backup_records(mock_db)
        assert len(result) == 2
        assert result[0]["status"] == "completed"

    async def test_get_record_found(self, mock_db):
        cursor = AsyncMock()
        cursor.fetchone.return_value = {"id": "1", "status": "completed"}
        mock_db.execute.return_value = cursor
        result = await get_backup_record(mock_db, "1")
        assert result is not None
        assert result["status"] == "completed"

    async def test_get_record_not_found(self, mock_db):
        cursor = AsyncMock()
        cursor.fetchone.return_value = None
        mock_db.execute.return_value = cursor
        result = await get_backup_record(mock_db, "nonexistent")
        assert result is None
