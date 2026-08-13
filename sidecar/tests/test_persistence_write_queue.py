"""Tests for write queue: WriteEnvelope, WriteQueue, barrier, and backpressure."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import aiosqlite
import pytest

from ibreeze.persistence.write_queue import WriteEnvelope, WriteQueue


class TestWriteEnvelope:
    @pytest.mark.asyncio
    async def test_is_expired_true(self) -> None:
        envelope = WriteEnvelope(
            "test",
            UUID(int=0),
            datetime.now(UTC) - timedelta(hours=1),
            lambda c: "ok",
        )
        assert envelope.is_expired() is True

    @pytest.mark.asyncio
    async def test_is_expired_false(self) -> None:
        envelope = WriteEnvelope(
            "test",
            UUID(int=0),
            datetime.now(UTC).replace(year=9999),
            lambda c: "ok",
        )
        assert envelope.is_expired() is False

    @pytest.mark.asyncio
    async def test_result_property(self) -> None:
        envelope = WriteEnvelope(
            "test",
            UUID(int=0),
            datetime.now(UTC).replace(year=9999),
            lambda c: "ok",
        )
        assert envelope.result is envelope.future


class TestWriteQueue:
    @pytest.fixture
    def mock_conn(self) -> AsyncMock:
        conn = AsyncMock(spec=aiosqlite.Connection)
        conn.execute = AsyncMock()
        conn.commit = AsyncMock()
        conn.rollback = AsyncMock()
        return conn

    async def test_submit_success(self, mock_conn: AsyncMock) -> None:
        queue = WriteQueue(mock_conn, capacity=32)

        async def my_execute(conn: aiosqlite.Connection) -> str:
            return "done"

        result = await queue.submit("test", UUID(int=0), datetime.now(UTC).replace(year=9999), my_execute)
        assert result == "done"
        mock_conn.commit.assert_awaited_once()
        await queue.stop()

    async def test_submit_queue_full(self, mock_conn: AsyncMock) -> None:
        queue = WriteQueue(mock_conn, capacity=1)
        hang_event = asyncio.Event()

        async def hang(_conn: aiosqlite.Connection) -> None:
            await hang_event.wait()

        task1 = asyncio.create_task(
            queue.submit("hang1", UUID(int=0), datetime.now(UTC).replace(year=9999), hang),
        )
        await asyncio.sleep(0.05)

        task2 = asyncio.create_task(
            queue.submit("hang2", UUID(int=0), datetime.now(UTC).replace(year=9999), hang),
        )
        await asyncio.sleep(0.05)

        with pytest.raises(RuntimeError, match="LOCAL_WRITE_BACKPRESSURE"):
            await queue.submit("hang3", UUID(int=0), datetime.now(UTC).replace(year=9999), hang)

        hang_event.set()
        await task1
        await task2
        await queue.stop()

    async def test_barrier_success(self, mock_conn: AsyncMock) -> None:
        queue = WriteQueue(mock_conn, capacity=32)
        await queue.barrier(timeout=10.0)
        await queue.stop()

    async def test_barrier_timeout(self, mock_conn: AsyncMock) -> None:
        async def idle_run() -> None:
            await asyncio.sleep(0)

        with patch.object(WriteQueue, "_run", side_effect=idle_run):
            queue = WriteQueue(mock_conn, capacity=32)
            with pytest.raises(RuntimeError, match="BACKUP_WRITE_BARRIER_TIMEOUT"):
                await queue.barrier(timeout=0.1)

    async def test_stop(self, mock_conn: AsyncMock) -> None:
        queue = WriteQueue(mock_conn, capacity=32)

        async def noop(_conn: aiosqlite.Connection) -> None:
            return None

        await queue.submit("noop", UUID(int=0), datetime.now(UTC).replace(year=9999), noop)
        await queue.stop()
        assert queue._worker_task is None

    async def test_depth(self, mock_conn: AsyncMock) -> None:
        queue = WriteQueue(mock_conn, capacity=32)
        assert queue.depth == 0
        await queue.stop()

    async def test_expired_envelope(self, mock_conn: AsyncMock) -> None:
        queue = WriteQueue(mock_conn, capacity=32)

        async def fake_execute(_conn: aiosqlite.Connection) -> str:
            return "ignored"

        with pytest.raises(RuntimeError, match="IPC_DEADLINE_EXCEEDED"):
            await queue.submit(
                "expired",
                UUID(int=0),
                datetime.now(UTC) - timedelta(hours=1),
                fake_execute,
            )
        await queue.stop()

    async def test_execution_exception(self, mock_conn: AsyncMock) -> None:
        queue = WriteQueue(mock_conn, capacity=32)

        async def fail(_conn: aiosqlite.Connection) -> None:
            raise ValueError("execution failed")

        with pytest.raises(ValueError, match="execution failed"):
            await queue.submit("fail", UUID(int=0), datetime.now(UTC).replace(year=9999), fail)

        mock_conn.rollback.assert_awaited_once()
        await queue.stop()
