from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from ibreeze.workers.spec import WorkerHealth
from ibreeze.workers.supervisor import WorkerEntry, WorkerSupervisor


class _MockWorker:
    def __init__(self, name: str = "MockWorker", **kwargs: object):
        self.name = name
        self._state = "stopped"
        self._heartbeat_at = ""
        self._last_success_at: str | None = None
        self._last_error_code: str | None = None
        self._restart_count = 0
        self._write_queue: object = kwargs.get("write_queue")

    async def _work_sleep(self) -> None:
        await asyncio.sleep(999)

    async def work(self) -> None:
        await self._work_sleep()

    def health(self) -> WorkerHealth:
        return WorkerHealth(
            name=self.name,
            state=self._state,
            heartbeat_at=self._heartbeat_at,
            last_success_at=self._last_success_at,
            last_error_code=self._last_error_code,
            restart_count=self._restart_count,
        )

    def update_heartbeat(self) -> None:
        self._heartbeat_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_success(self) -> None:
        self._last_success_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_error(self, code: str) -> None:
        self._last_error_code = code


WORKER_CLASS_NAMES = [
    "RuntimeWorker",
    "AnalysisWorker",
    "OutboxWorker",
    "KnowledgeWorker",
    "ReconciliationWorker",
    "BackupWorker",
    "EventCompactionWorker",
]


@pytest_asyncio.fixture
async def patched_supervisor():
    patchers = []
    mock_classes = {}
    for name in WORKER_CLASS_NAMES:
        p = patch(f"ibreeze.workers.supervisor.{name}")
        mc = p.start()
        patchers.append(p)
        mock_classes[name] = mc

    writer = AsyncMock()
    wq = AsyncMock()
    sup = WorkerSupervisor(writer=writer, write_queue=wq)

    for name, mc in mock_classes.items():
        mc.side_effect = lambda *a, name=name, **kw: _MockWorker(name=name, **kw)

    yield sup, wq, mock_classes

    await sup.stop()
    for p in patchers:
        p.stop()


class TestWorkerSupervisor:
    def test_init_stores_writer_and_write_queue(self):
        writer = AsyncMock()
        wq = AsyncMock()
        sup = WorkerSupervisor(writer=writer, write_queue=wq)
        assert sup._writer is writer
        assert sup._write_queue is wq
        assert sup._workers == []
        assert sup._tasks == []

    def test_init_with_empty_workers_and_tasks(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        assert len(sup._workers) == 0
        assert len(sup._tasks) == 0

    @pytest.mark.asyncio
    async def test_start_creates_all_worker_types(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0.05)
        assert len(sup._workers) == len(WORKER_CLASS_NAMES)
        for cls_name in WORKER_CLASS_NAMES:
            mock_classes[cls_name].assert_called_once()

    @pytest.mark.asyncio
    async def test_start_worker_names_match(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0.05)

        worker_names = [e.worker.name for e in sup._workers]
        for expected in WORKER_CLASS_NAMES:
            assert expected in worker_names

    @pytest.mark.asyncio
    async def test_start_creates_tasks_for_each_worker(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0.05)
        assert len(sup._tasks) == len(WORKER_CLASS_NAMES)
        assert all(not t.done() for t in sup._tasks)

    @pytest.mark.asyncio
    async def test_stop_cancels_all_tasks(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0.05)
        await sup.stop()
        assert all(t.done() for t in sup._tasks)
        assert sup._tasks == []

    @pytest.mark.asyncio
    async def test_stop_without_start_does_not_raise(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        await sup.stop()

    @pytest.mark.asyncio
    async def test_stop_worker_state_becomes_stopped(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0.05)
        await sup.stop()
        for entry in sup._workers:
            assert entry.worker._state == "stopped"

    @pytest.mark.asyncio
    async def test_health_returns_snapshot_for_each_worker(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0.05)

        results = sup.health()
        assert len(results) == len(WORKER_CLASS_NAMES)
        for wh in results:
            assert isinstance(wh, WorkerHealth)
            assert wh.name in WORKER_CLASS_NAMES

    @pytest.mark.asyncio
    async def test_health_workers_starting_then_healthy(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0)
        results = sup.health()
        for wh in results:
            assert wh.state in ("starting", "healthy")

    def test_health_stale_heartbeat_marks_failed(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        worker = _MockWorker(name="TestWorker")
        worker._heartbeat_at = "2020-01-01T00:00:00Z"
        worker._state = "healthy"
        sup._workers.append(WorkerEntry(worker=worker))

        results = sup.health()
        assert results[0].state == "failed"

    def test_health_invalid_heartbeat_marks_failed(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        worker = _MockWorker(name="TestWorker")
        worker._heartbeat_at = "not-a-valid-date"
        worker._state = "healthy"
        sup._workers.append(WorkerEntry(worker=worker))

        results = sup.health()
        assert results[0].state == "failed"

    def test_health_recent_heartbeat_preserves_state(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        worker = _MockWorker(name="TestWorker")
        worker._heartbeat_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        worker._state = "healthy"
        sup._workers.append(WorkerEntry(worker=worker))

        results = sup.health()
        assert results[0].state == "healthy"

    def test_health_empty_heartbeat_string_preserves_state(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        worker = _MockWorker(name="TestWorker")
        worker._heartbeat_at = ""
        worker._state = "starting"
        sup._workers.append(WorkerEntry(worker=worker))

        results = sup.health()
        assert results[0].state == "starting"

    @pytest.mark.asyncio
    async def test_multiple_workers_concurrent(self, patched_supervisor):
        sup, wq, mock_classes = patched_supervisor
        await sup.start()
        await asyncio.sleep(0.05)
        assert len(sup._tasks) == 7
        assert all(not t.done() for t in sup._tasks)

        worker_states = [e.worker._state for e in sup._workers]
        assert all(s in ("starting", "healthy") for s in worker_states)

        await sup.stop()
        assert all(e.worker._state == "stopped" for e in sup._workers)

    @pytest.mark.asyncio
    async def test_worker_recovers_from_exception(self):
        sup = WorkerSupervisor(writer=AsyncMock(), write_queue=AsyncMock())
        sup.BACKOFF_SECONDS = [0.05]

        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise RuntimeError("transient")
            await asyncio.sleep(0.01)

        worker = _MockWorker(name="FailWorker")
        worker.work = fail_then_succeed
        entry = WorkerEntry(worker=worker)
        sup._workers.append(entry)
        task = asyncio.create_task(sup._run_worker(entry))
        sup._tasks.append(task)

        await asyncio.sleep(0.3)

        assert entry.worker._last_error_code == "transient"
        assert entry.worker._state == "healthy"

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_worker_entry(self):
        worker = _MockWorker(name="TestWorker")
        entry = WorkerEntry(worker=worker)
        assert entry.worker is worker
