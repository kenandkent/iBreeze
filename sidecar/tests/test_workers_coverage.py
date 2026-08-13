"""Coverage tests for ibreeze.workers.spec, ibreeze.workers.runtime, ibreeze.workers.supervisor.

Targets the uncovered lines:
- spec.py: inner write-queue closures _index_pending / _reconcile / _rotate_backups / _compact
- runtime.py: the executor-backed work() path
- supervisor.py: max-restart backoff loop and cancellation during backoff sleep
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.runtime import RuntimeWorker
from ibreeze.workers.spec import (
    BackupWorker,
    EventCompactionWorker,
    KnowledgeWorker,
    ReconciliationWorker,
    WorkerHealth,
)
from ibreeze.workers.supervisor import WorkerEntry, WorkerSupervisor


def _capture_submit_conn(conn: AsyncMock) -> tuple[AsyncMock, dict[str, object]]:
    """Return (write_queue, capture) where submit invokes the closure against ``conn``."""
    captured: dict[str, object] = {}

    async def submit_side_effect(*args, **_kwargs):
        fn = args[3]
        captured["fn"] = fn
        result = await fn(conn)
        captured["result"] = result
        return result

    wq = AsyncMock(spec=WriteQueue)
    wq.submit = AsyncMock(side_effect=submit_side_effect)
    return wq, captured


def _conn_with(execute_returns: list[object]) -> AsyncMock:
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=execute_returns)
    return conn


# ── spec.py: KnowledgeWorker._index_pending (78-84) ────────────────────────


class TestKnowledgeWorkerIndexPending:
    async def test_runs_query_and_returns_zero(self):
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"cnt": 5})
        conn = _conn_with([cursor])
        wq, captured = _capture_submit_conn(conn)
        w = KnowledgeWorker(write_queue=wq)
        await w.work()

        assert captured["result"] == 0
        conn.execute.assert_awaited_once()
        sql = conn.execute.await_args.args[0]
        assert "FROM knowledge_items" in sql
        assert "embedding_generation_id IS NULL" in sql
        cursor.fetchone.assert_awaited_once()


# ── spec.py: ReconciliationWorker._reconcile (108-121) ─────────────────────


class TestReconciliationWorkerReconcile:
    async def test_issues_raised_when_thresholds_exceeded(self):
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[{"cnt": 5000}, {"cnt": 500}])
        conn = _conn_with([cursor, cursor])
        wq, captured = _capture_submit_conn(conn)
        w = ReconciliationWorker(write_queue=wq)
        with patch("ibreeze.workers.spec.logger") as mock_logger:
            await w.work()
        assert captured["result"] == 2
        assert mock_logger.warning.call_count == 2

    async def test_no_issues_when_within_thresholds(self):
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[{"cnt": 10}, {"cnt": 5}])
        conn = _conn_with([cursor, cursor])
        wq, captured = _capture_submit_conn(conn)
        w = ReconciliationWorker(write_queue=wq)
        await w.work()
        assert captured["result"] == 0

    async def test_no_rows_defaults_to_zero(self):
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(side_effect=[None, None])
        conn = _conn_with([cursor, cursor])
        wq, captured = _capture_submit_conn(conn)
        w = ReconciliationWorker(write_queue=wq)
        await w.work()
        assert captured["result"] == 0


# ── spec.py: BackupWorker._rotate_backups (147-152) ────────────────────────


class TestBackupWorkerRotateBackups:
    async def test_runs_query_and_returns_zero(self):
        cursor = AsyncMock()
        conn = _conn_with([cursor])
        wq, captured = _capture_submit_conn(conn)
        w = BackupWorker(write_queue=wq)
        await w.work()

        assert captured["result"] == 0
        conn.execute.assert_awaited_once()
        sql = conn.execute.await_args.args[0]
        assert "FROM backup_records" in sql


# ── spec.py: EventCompactionWorker._compact (174-199) ──────────────────────


class TestEventCompactionWorkerCompact:
    async def test_deletes_domain_events_when_old_events_exceed_threshold(self):
        del_outbox = AsyncMock()
        del_outbox.rowcount = 7
        count_events = AsyncMock()
        count_events.fetchone = AsyncMock(return_value={"cnt": 50000})
        del_domain = AsyncMock()
        del_domain.rowcount = 3
        conn = _conn_with([del_outbox, count_events, del_domain])
        wq, captured = _capture_submit_conn(conn)
        w = EventCompactionWorker(write_queue=wq)
        await w.work()

        assert captured["result"] == 10
        assert conn.execute.await_count == 3

    async def test_skips_domain_delete_when_under_threshold(self):
        del_outbox = AsyncMock()
        del_outbox.rowcount = 4
        count_events = AsyncMock()
        count_events.fetchone = AsyncMock(return_value={"cnt": 5})
        conn = _conn_with([del_outbox, count_events])
        wq, captured = _capture_submit_conn(conn)
        w = EventCompactionWorker(write_queue=wq)
        await w.work()

        assert captured["result"] == 4
        assert conn.execute.await_count == 2

    async def test_missing_count_row_defaults_to_zero(self):
        del_outbox = AsyncMock()
        del_outbox.rowcount = 2
        count_events = AsyncMock()
        count_events.fetchone = AsyncMock(return_value=None)
        conn = _conn_with([del_outbox, count_events])
        wq, captured = _capture_submit_conn(conn)
        w = EventCompactionWorker(write_queue=wq)
        await w.work()

        assert captured["result"] == 2


# ── runtime.py: executor-backed work() path (58-65) ────────────────────────


def _executor_worker() -> RuntimeWorker:
    read_pool = AsyncMock()
    wq = AsyncMock(spec=WriteQueue)
    worker = RuntimeWorker(write_queue=wq, read_pool=read_pool)
    assert worker._executor is not None
    return worker


class TestRuntimeWorkerExecutorPath:
    async def test_no_work_when_count_zero(self):
        worker = _executor_worker()
        worker._executor.work = AsyncMock(return_value=0)
        await worker.work()
        worker._executor.work.assert_awaited_once()
        assert worker._executor.work.await_args.args[0] is not None  # heartbeat passed

    async def test_logs_count_when_runs_executed(self):
        worker = _executor_worker()
        worker._executor.work = AsyncMock(return_value=1)
        with patch("ibreeze.workers.runtime.logger") as mock_logger:
            await worker.work()
        mock_logger.info.assert_called_once_with("RuntimeWorker executed %d run", 1)

    async def test_logs_exception_on_failure(self):
        worker = _executor_worker()
        worker._executor.work = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("ibreeze.workers.runtime.logger") as mock_logger:
            await worker.work()
        mock_logger.exception.assert_called_once_with("RuntimeWorker execution failed")

    async def test_re_raises_cancelled_error(self):
        worker = _executor_worker()
        worker._executor.work = AsyncMock(side_effect=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await worker.work()


# ── supervisor.py: _run_worker restart handling (125-132, 138-140) ─────────


class _FailingWorker:
    name = "FailWorker"

    def __init__(self, name: str = "FailWorker") -> None:
        self.name = name
        self._state = "stopped"
        self._heartbeat_at = ""
        self._last_success_at: str | None = None
        self._last_error_code: str | None = None
        self._restart_count = 0

    async def work(self) -> None:
        raise RuntimeError("boom")

    def update_heartbeat(self) -> None:
        self._heartbeat_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_success(self) -> None:
        self._last_success_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_error(self, code: str) -> None:
        self._last_error_code = code

    def health(self) -> WorkerHealth:
        return WorkerHealth(
            name=self.name,
            state=self._state,
            heartbeat_at=self._heartbeat_at,
            last_success_at=self._last_success_at,
            last_error_code=self._last_error_code,
            restart_count=self._restart_count,
        )


class TestWorkerSupervisorRestart:
    async def test_max_restarts_enters_backoff_loop_then_cancelled(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        sup.BACKOFF_SECONDS = [0.01]
        sup.MAX_RESTARTS_IN_5MIN = 2
        worker = _FailingWorker("RestartWorker")
        entry = WorkerEntry(worker=worker)
        sup._workers.append(entry)

        task = asyncio.create_task(sup._run_worker(entry))
        await asyncio.sleep(0.3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert worker._state == "stopped"
        assert worker._last_error_code is not None

    async def test_cancel_during_backoff_sleep_marks_stopped(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        sup.BACKOFF_SECONDS = [30]
        worker = _FailingWorker("BackoffWorker")
        entry = WorkerEntry(worker=worker)
        sup._workers.append(entry)

        task = asyncio.create_task(sup._run_worker(entry))
        await asyncio.sleep(0.2)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert worker._state == "stopped"
