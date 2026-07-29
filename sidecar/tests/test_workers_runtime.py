from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from ibreeze.workers.runtime import RuntimeWorker


class TestRuntimeWorkerInit:
    def test_name(self):
        w = RuntimeWorker()
        assert w.name == "RuntimeWorker"

    def test_health_initial(self):
        w = RuntimeWorker()
        h = w.health()
        assert h.name == "RuntimeWorker"
        assert h.state == "stopped"

    def test_write_queue_default_none(self):
        w = RuntimeWorker()
        assert w._write_queue is None


class TestRuntimeWorkerWorkNoWriteQueue:
    async def test_sleeps_when_no_wq(self):
        w = RuntimeWorker()
        start = datetime.now(UTC)
        await w.work()
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.9


class TestRuntimeWorkerWorkSuccess:
    @patch("ibreeze.workers.runtime.logger")
    async def test_submits_tick_task(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock()
        w = RuntimeWorker(write_queue=wq)
        await w.work()

        wq.submit.assert_awaited_once()
        args, _ = wq.submit.await_args
        assert args[0] == "runtime.dispatch_ready"
        assert isinstance(args[1], UUID)
        assert args[1].int == 0

    @patch("ibreeze.workers.runtime.logger")
    async def test_inner_dispatch_ready_queries_db(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value=cursor)

        captured_fn = None

        async def submit_side_effect(*args, **_kwargs):
            nonlocal captured_fn
            captured_fn = args[3]
            return await captured_fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = RuntimeWorker(write_queue=wq)
        await w.work()

        assert captured_fn is not None
        result = await captured_fn(conn)
        assert result == 0
        assert conn.execute.call_count >= 1
        sql = conn.execute.call_args[0][0]
        assert "FROM runtime_queue" in sql
        assert "status='ready'" in sql

    @patch("ibreeze.workers.runtime.logger")
    async def test_deadline_is_about_30_seconds(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock()
        w = RuntimeWorker(write_queue=wq)
        await w.work()

        args, _ = wq.submit.await_args
        deadline = args[2]
        now = datetime.now(UTC)
        assert deadline > now
        assert (deadline - now).total_seconds() > 20
        assert (deadline - now).total_seconds() < 30


class TestRuntimeWorkerWorkException:
    @patch("ibreeze.workers.runtime.logger")
    async def test_logs_exception_on_failure(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=RuntimeError("db down"))
        w = RuntimeWorker(write_queue=wq)
        await w.work()
        mock_logger.exception.assert_called_once_with(
            "RuntimeWorker dispatch failed"
        )

    @patch("ibreeze.workers.runtime.logger")
    async def test_does_not_re_raise(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=RuntimeError("db down"))
        w = RuntimeWorker(write_queue=wq)
        try:
            await w.work()
        except Exception:
            pytest.fail("work() should not re-raise exceptions")
