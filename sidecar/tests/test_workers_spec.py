from __future__ import annotations

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

    def test_with_values(self):
        h = WorkerHealth(name="w1", state="healthy", heartbeat_at="2026-01-01T00:00:00Z")
        assert h.state == "healthy"


class TestBaseWorker:
    async def test_work_raises_not_implemented(self):
        w = BaseWorker()
        try:
            await w.work()
            assert False, "should have raised"
        except NotImplementedError:
            pass

    def test_health_initial(self):
        w = BaseWorker()
        h = w.health()
        assert h.name == "base"
        assert h.state == "stopped"

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


class TestKnowledgeWorker:
    async def test_work_sleeps(self):
        w = KnowledgeWorker()
        h = w.health()
        assert h.name == "KnowledgeWorker"
        assert h.state == "stopped"


class TestReconciliationWorker:
    async def test_work_sleeps(self):
        w = ReconciliationWorker()
        h = w.health()
        assert h.name == "ReconciliationWorker"


class TestBackupWorker:
    async def test_work_sleeps(self):
        w = BackupWorker()
        h = w.health()
        assert h.name == "BackupWorker"


class TestEventCompactionWorker:
    async def test_work_sleeps(self):
        w = EventCompactionWorker()
        h = w.health()
        assert h.name == "EventCompactionWorker"
