"""Coverage tests for ibreeze/persistence/write_queue.py (uncovered branches)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import aiosqlite
import pytest

from ibreeze.persistence.write_queue import WriteEnvelope, WriteQueue


def _future_deadline() -> datetime:
    return datetime.now(UTC).replace(year=9999)


def _past_deadline() -> datetime:
    return datetime.now(UTC) - timedelta(hours=1)


@pytest.fixture
def mock_conn() -> AsyncMock:
    conn = AsyncMock(spec=aiosqlite.Connection)
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    conn.rollback = AsyncMock()
    return conn


class _ScriptedQueue:
    """Deterministic queue stand-in: yields scripted envelopes, then times out.

    The real worker task is stopped first so only the directly-driven ``_run()``
    loop observes this queue.  ``task_done`` is tracked so the loop's accounting
    never trips asyncio's "task_done called too many times" guard.
    """

    def __init__(self, envelopes, *, timeouts_first: int = 0) -> None:
        self._items = list(envelopes)
        self._pending_timeouts = timeouts_first
        self.done_count = 0

    def put_nowait(self, item) -> None:
        self._items.append(item)

    async def get(self):
        if self._pending_timeouts > 0:
            self._pending_timeouts -= 1
            raise TimeoutError()
        if self._items:
            return self._items.pop(0)
        raise TimeoutError()

    def task_done(self) -> None:
        self.done_count += 1

    async def join(self) -> None:
        return None

    def qsize(self) -> int:
        return len(self._items)


async def _drive_run(mock_conn, envelopes):
    """Stop the real worker then drive _run() directly over a scripted queue."""
    queue = WriteQueue(mock_conn, capacity=32)
    await queue.stop()
    queue._queue = _ScriptedQueue(envelopes)
    await queue._run()
    return queue


class TestSubmitAfterStop:
    @pytest.mark.asyncio
    async def test_submit_after_stop_raises(self, mock_conn):
        queue = WriteQueue(mock_conn, capacity=32)
        await queue.stop()

        async def noop(_conn):
            return None

        with pytest.raises(RuntimeError, match="LOCAL_WRITE_QUEUE_STOPPED"):
            await queue.submit("x", UUID(int=0), _future_deadline(), noop)


class TestStopBranches:
    @pytest.mark.asyncio
    async def test_stop_twice_is_idempotent(self, mock_conn):
        queue = WriteQueue(mock_conn, capacity=32)
        await queue.stop()
        await queue.stop()  # second stop: worker_task is None -> exit

    @pytest.mark.asyncio
    async def test_stop_join_timeout_is_swallowed(self, mock_conn):
        async def idle_run() -> None:
            await asyncio.sleep(0)

        with patch.object(WriteQueue, "_run", side_effect=idle_run):
            queue = WriteQueue(mock_conn, capacity=32)
            # An unprocessed item keeps queue.join() pending past the timeout.
            queue._queue.put_nowait(
                WriteEnvelope("stuck", UUID(int=0), _future_deadline(), lambda _conn: None)
            )
            await queue.stop(timeout=0.05)  # TimeoutError -> pass
        assert queue._worker_task is None


class TestRunWorkerBranches:
    @pytest.mark.asyncio
    async def test_get_timeout_breaks_when_stopped(self, mock_conn):
        # No envelopes: the first get() times out and _running is False -> break.
        queue = WriteQueue(mock_conn, capacity=32)
        await queue.stop()
        queue._queue = _ScriptedQueue([])
        await queue._run()

    @pytest.mark.asyncio
    async def test_timeout_continue_while_running(self, mock_conn):
        # A get() timeout while still running must continue (not break); the
        # envelope's execute turns _running off so the loop exits afterwards.
        queue = WriteQueue(mock_conn, capacity=32)
        await queue.stop()
        queue._running = True

        async def execute(_conn):
            queue._running = False
            return "ok"

        env = WriteEnvelope("x", UUID(int=0), _future_deadline(), execute)
        scripted = _ScriptedQueue([env], timeouts_first=1)
        queue._queue = scripted
        await queue._run()
        assert scripted.done_count == 1
        mock_conn.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancelled_envelope_skipped(self, mock_conn):
        env = WriteEnvelope("x", UUID(int=0), _future_deadline(), lambda _conn: None)
        env.future.cancel()
        await _drive_run(mock_conn, [env])

    @pytest.mark.asyncio
    async def test_expired_envelope_with_done_future(self, mock_conn):
        # future already done -> set_exception must be skipped (line 121->123).
        env = WriteEnvelope("x", UUID(int=0), _past_deadline(), lambda _conn: None)
        env.future.set_result("pre-resolved")
        await _drive_run(mock_conn, [env])

    @pytest.mark.asyncio
    async def test_success_envelope_with_done_future(self, mock_conn):
        # future already done -> set_result must be skipped (line 129->139).
        async def execute(_conn):
            return "ok"

        env = WriteEnvelope("x", UUID(int=0), _future_deadline(), execute)
        env.future.set_result("pre-resolved")
        await _drive_run(mock_conn, [env])
        mock_conn.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_failure_swallowed(self, mock_conn):
        async def fail(_conn):
            raise ValueError("boom")

        env = WriteEnvelope("x", UUID(int=0), _future_deadline(), fail)
        mock_conn.rollback = AsyncMock(side_effect=RuntimeError("rollback failed"))
        await _drive_run(mock_conn, [env])
        assert env.future.exception() is not None

    @pytest.mark.asyncio
    async def test_execution_error_with_done_future(self, mock_conn):
        # future already done -> set_exception must be skipped (line 136->139).
        async def fail(_conn):
            raise ValueError("boom")

        env = WriteEnvelope("x", UUID(int=0), _future_deadline(), fail)
        env.future.set_result("pre-resolved")
        await _drive_run(mock_conn, [env])
        mock_conn.rollback.assert_awaited_once()
