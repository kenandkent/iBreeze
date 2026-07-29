from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.runtime import RuntimeWorker
from ibreeze.workers.spec import (
    BackupWorker,
    BaseWorker,
    EventCompactionWorker,
    KnowledgeWorker,
    ReconciliationWorker,
    WorkerHealth,
)


class TestWorkerHealth:
    def test_default_state(self):
        h = WorkerHealth(name="test")
        assert h.name == "test"
        assert h.state == "stopped"
        assert h.heartbeat_at == ""
        assert h.last_success_at is None
        assert h.last_error_code is None
        assert h.queue_lag == 0
        assert h.restart_count == 0

    def test_with_values(self):
        h = WorkerHealth(
            name="w1",
            state="healthy",
            heartbeat_at="2026-01-01T00:00:00Z",
            last_success_at="2026-01-01T12:00:00Z",
            last_error_code="ERR_BOOT",
            queue_lag=7,
            restart_count=3,
        )
        assert h.name == "w1"
        assert h.state == "healthy"
        assert h.heartbeat_at == "2026-01-01T00:00:00Z"
        assert h.last_success_at == "2026-01-01T12:00:00Z"
        assert h.last_error_code == "ERR_BOOT"
        assert h.queue_lag == 7
        assert h.restart_count == 3


class TestBaseWorker:
    async def test_work_raises_not_implemented(self):
        w = BaseWorker()
        with pytest.raises(NotImplementedError):
            await w.work()

    def test_name_class_var(self):
        assert BaseWorker.name == "base"

    def test_health_initial(self):
        w = BaseWorker()
        h = w.health()
        assert h.name == "base"
        assert h.state == "stopped"
        assert h.heartbeat_at == ""
        assert h.last_success_at is None
        assert h.last_error_code is None
        assert h.restart_count == 0

    def test_update_heartbeat_sets_time(self):
        w = BaseWorker()
        w.update_heartbeat()
        assert w._heartbeat_at != ""

    def test_mark_success_sets_time(self):
        w = BaseWorker()
        w.mark_success()
        assert w._last_success_at is not None

    def test_mark_error_sets_code(self):
        w = BaseWorker()
        w.mark_error("SOME_ERROR")
        assert w._last_error_code == "SOME_ERROR"

    def test_mark_error_overwrites(self):
        w = BaseWorker()
        w.mark_error("ERR1")
        w.mark_error("ERR2")
        assert w._last_error_code == "ERR2"

    def test_health_reflects_mutations(self):
        w = BaseWorker()
        w.update_heartbeat()
        w.mark_success()
        h = w.health()
        assert h.heartbeat_at != ""
        assert h.last_success_at is not None

    def test_health_restart_count_starts_at_zero(self):
        w = BaseWorker()
        assert w._restart_count == 0


class TestKnowledgeWorker:
    def test_name(self):
        w = KnowledgeWorker()
        assert w.health().name == "KnowledgeWorker"

    async def test_work_without_write_queue_returns_immediately(self):
        w = KnowledgeWorker()
        await w.work()

    async def test_work_with_write_queue_submits_index_task(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=5)
        w = KnowledgeWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        assert wq.submit.call_args[0][0] == "knowledge.index_pending"

    async def test_work_with_write_queue_no_items(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=0)
        w = KnowledgeWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    async def test_work_with_write_queue_exception_caught(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(side_effect=RuntimeError("db failure"))
        w = KnowledgeWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    def test_health_initial_state(self):
        w = KnowledgeWorker()
        assert w.health().state == "stopped"


class TestReconciliationWorker:
    def test_name(self):
        w = ReconciliationWorker()
        assert w.health().name == "ReconciliationWorker"

    async def test_work_without_write_queue_returns_immediately(self):
        w = ReconciliationWorker()
        await w.work()

    async def test_work_with_write_queue_submits_reconcile_task(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=2)
        w = ReconciliationWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        assert wq.submit.call_args[0][0] == "reconciliation.verify"

    async def test_work_with_write_queue_no_issues(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=0)
        w = ReconciliationWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    async def test_work_with_write_queue_exception_caught(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(side_effect=RuntimeError("db failure"))
        w = ReconciliationWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    def test_health_initial_state(self):
        w = ReconciliationWorker()
        assert w.health().state == "stopped"


class TestBackupWorker:
    def test_name(self):
        w = BackupWorker()
        assert w.health().name == "BackupWorker"

    async def test_work_without_write_queue_returns_immediately(self):
        w = BackupWorker()
        await w.work()

    async def test_work_with_write_queue_submits_rotate_task(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=1)
        w = BackupWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        assert wq.submit.call_args[0][0] == "backup.rotate"

    async def test_work_with_write_queue_no_rotation(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=0)
        w = BackupWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    async def test_work_with_write_queue_exception_caught(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(side_effect=RuntimeError("db failure"))
        w = BackupWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    def test_health_initial_state(self):
        w = BackupWorker()
        assert w.health().state == "stopped"


class TestEventCompactionWorker:
    def test_name(self):
        w = EventCompactionWorker()
        assert w.health().name == "EventCompactionWorker"

    async def test_work_without_write_queue_returns_immediately(self):
        w = EventCompactionWorker()
        await w.work()

    async def test_work_with_write_queue_submits_compact_task(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=100)
        w = EventCompactionWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        assert wq.submit.call_args[0][0] == "event.compact"

    async def test_work_with_write_queue_no_events(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=0)
        w = EventCompactionWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    async def test_work_with_write_queue_exception_caught(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(side_effect=RuntimeError("db failure"))
        w = EventCompactionWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    def test_health_initial_state(self):
        w = EventCompactionWorker()
        assert w.health().state == "stopped"


class TestRuntimeWorker:
    def test_name(self):
        w = RuntimeWorker()
        assert w.health().name == "RuntimeWorker"

    async def test_work_without_write_queue_sleeps_and_returns(self):
        w = RuntimeWorker()
        with patch("ibreeze.workers.runtime.asyncio.sleep", AsyncMock()):
            await w.work()

    async def test_work_with_write_queue_submits_dispatch_task(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=3)
        w = RuntimeWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        assert wq.submit.call_args[0][0] == "runtime.dispatch_ready"

    async def test_work_with_write_queue_no_items(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(return_value=0)
        w = RuntimeWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    async def test_work_with_write_queue_exception_caught(self):
        wq = AsyncMock(spec=WriteQueue)
        wq.submit = AsyncMock(side_effect=RuntimeError("db failure"))
        w = RuntimeWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()

    def test_health_initial_state(self):
        w = RuntimeWorker()
        assert w.health().state == "stopped"
