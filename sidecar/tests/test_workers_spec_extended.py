"""Extended tests for ibreeze.workers.spec module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ibreeze.workers.spec import (
    BackupWorker,
    BaseWorker,
    EventCompactionWorker,
    KnowledgeWorker,
    ReconciliationWorker,
    WorkerHealth,
)


class TestWorkerHealth:
    def test_defaults(self):
        h = WorkerHealth(name="test")
        assert h.name == "test"
        assert h.state == "stopped"
        assert h.heartbeat_at == ""
        assert h.last_success_at is None
        assert h.last_error_code is None
        assert h.queue_lag == 0
        assert h.restart_count == 0

    def test_custom_values(self):
        h = WorkerHealth(
            name="w1",
            state="running",
            heartbeat_at="2026-01-01T00:00:00Z",
            last_success_at="2026-01-01T00:01:00Z",
            last_error_code="ERR",
            queue_lag=5,
            restart_count=3,
        )
        assert h.state == "running"
        assert h.restart_count == 3


class TestBaseWorker:
    def test_health_returns_worker_health(self):
        w = BaseWorker()
        h = w.health()
        assert isinstance(h, WorkerHealth)
        assert h.name == "base"
        assert h.state == "stopped"

    async def test_work_raises_not_implemented(self):
        w = BaseWorker()
        with pytest.raises(NotImplementedError):
            await w.work()

    def test_update_heartbeat(self):
        w = BaseWorker()
        w.update_heartbeat()
        h = w.health()
        assert h.heartbeat_at != ""

    def test_mark_success(self):
        w = BaseWorker()
        w.mark_success()
        h = w.health()
        assert h.last_success_at is not None

    def test_mark_error(self):
        w = BaseWorker()
        w.mark_error("SOME_ERROR")
        h = w.health()
        assert h.last_error_code == "SOME_ERROR"


class TestKnowledgeWorker:
    def test_name(self):
        w = KnowledgeWorker()
        assert w.name == "KnowledgeWorker"

    async def test_work_with_none_write_queue(self):
        w = KnowledgeWorker(write_queue=None)
        # Should not raise
        await w.work()

    async def test_work_submits_to_write_queue(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=5)
        w = KnowledgeWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        call_args = wq.submit.call_args
        assert call_args[0][0] == "knowledge.index_pending"

    async def test_work_handles_exception(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=Exception("db error"))
        w = KnowledgeWorker(write_queue=wq)
        # Should not raise
        await w.work()


class TestReconciliationWorker:
    def test_name(self):
        w = ReconciliationWorker()
        assert w.name == "ReconciliationWorker"

    async def test_work_with_none_write_queue(self):
        w = ReconciliationWorker(write_queue=None)
        await w.work()

    async def test_work_submits_to_write_queue(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=0)
        w = ReconciliationWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        call_args = wq.submit.call_args
        assert call_args[0][0] == "reconciliation.verify"

    async def test_work_handles_exception(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=Exception("fail"))
        w = ReconciliationWorker(write_queue=wq)
        await w.work()


class TestBackupWorker:
    def test_name(self):
        w = BackupWorker()
        assert w.name == "BackupWorker"

    async def test_work_with_none_write_queue(self):
        w = BackupWorker(write_queue=None)
        await w.work()

    async def test_work_submits_to_write_queue(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=1)
        w = BackupWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        call_args = wq.submit.call_args
        assert call_args[0][0] == "backup.rotate"

    async def test_work_handles_exception(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=Exception("backup fail"))
        w = BackupWorker(write_queue=wq)
        await w.work()


class TestEventCompactionWorker:
    def test_name(self):
        w = EventCompactionWorker()
        assert w.name == "EventCompactionWorker"

    async def test_work_with_none_write_queue(self):
        w = EventCompactionWorker(write_queue=None)
        await w.work()

    async def test_work_submits_to_write_queue(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=10)
        w = EventCompactionWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        call_args = wq.submit.call_args
        assert call_args[0][0] == "event.compact"

    async def test_work_handles_exception(self):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=Exception("compact fail"))
        w = EventCompactionWorker(write_queue=wq)
        await w.work()
