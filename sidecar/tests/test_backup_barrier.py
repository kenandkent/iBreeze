from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from ibreeze.backup.barrier import acquire_backup_barrier


@pytest.mark.asyncio
class TestAcquireBackupBarrier:
    async def test_barrier_success(self):
        mock_writer = AsyncMock()
        mock_write_queue = AsyncMock()
        mock_write_queue.barrier = AsyncMock()

        async with acquire_backup_barrier(
            mock_writer, mock_write_queue, timeout=timedelta(seconds=5)
        ):
            pass

        mock_write_queue.barrier.assert_awaited_once()
        mock_writer.execute.assert_awaited_once_with("PRAGMA wal_checkpoint(TRUNCATE)")

    async def test_barrier_timeout_raises(self):
        mock_writer = AsyncMock()
        mock_write_queue = AsyncMock()
        mock_write_queue.barrier = AsyncMock(side_effect=TimeoutError)

        with pytest.raises(RuntimeError, match="BACKUP_WRITE_BARRIER_TIMEOUT"):
            async with acquire_backup_barrier(
                mock_writer, mock_write_queue, timeout=timedelta(seconds=1)
            ):
                pass

    async def test_barrier_runtime_error_raises(self):
        mock_writer = AsyncMock()
        mock_write_queue = AsyncMock()
        mock_write_queue.barrier = AsyncMock(side_effect=RuntimeError)

        with pytest.raises(RuntimeError, match="BACKUP_WRITE_BARRIER_TIMEOUT"):
            async with acquire_backup_barrier(
                mock_writer, mock_write_queue, timeout=timedelta(seconds=1)
            ):
                pass

    async def test_barrier_default_timeout(self):
        mock_writer = AsyncMock()
        mock_write_queue = AsyncMock()
        mock_write_queue.barrier = AsyncMock()

        async with acquire_backup_barrier(mock_writer, mock_write_queue):
            pass

        mock_write_queue.barrier.assert_awaited_once()
