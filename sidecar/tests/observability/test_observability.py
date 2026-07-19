"""ObservabilityService 测试。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from acos.observability.models import DashboardMetric
from acos.observability.service import ObservabilityService
from acos.store.migrator import Migrator


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    migrator = Migrator(str(p))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(p)


@pytest.fixture
def svc(db_path: str) -> ObservabilityService:
    return ObservabilityService(db_path)


async def _insert_task(db_path: str, task_id: str, company_id: str = "comp-1", **extra: object) -> None:
    defaults = {
        "task_id": task_id,
        "company_id": company_id,
        "title": f"Task {task_id}",
        "priority": 5,
        "status": "created",
    }
    defaults.update(extra)  # type: ignore[arg-type]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO tasks
               (task_id, company_id, title, priority, status, version)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (defaults["task_id"], defaults["company_id"], defaults["title"],
             defaults["priority"], defaults["status"]),
        )
        await db.commit()


# ── TaskReadModel ──


async def test_update_and_get_task_read_model(svc: ObservabilityService, db_path: str) -> None:
    await _insert_task(db_path, "task-1")
    await svc.update_task_read_model("task-1")
    model = await svc.get_task_read_model("task-1")
    assert model is not None
    assert model.task_id == "task-1"
    assert model.title == "Task task-1"
    assert model.progress_pct == 0.0


async def test_update_task_read_model_completed(svc: ObservabilityService, db_path: str) -> None:
    await _insert_task(db_path, "task-1", status="completed")
    await svc.update_task_read_model("task-1")
    model = await svc.get_task_read_model("task-1")
    assert model is not None
    assert model.progress_pct == 100.0


async def test_update_task_read_model_upsert(svc: ObservabilityService, db_path: str) -> None:
    await _insert_task(db_path, "task-1")
    await svc.update_task_read_model("task-1")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE tasks SET title = 'Updated Title' WHERE task_id = 'task-1'")
        await db.commit()
    await svc.update_task_read_model("task-1")
    model = await svc.get_task_read_model("task-1")
    assert model is not None
    assert model.title == "Updated Title"


async def test_get_task_read_model_nonexistent(svc: ObservabilityService) -> None:
    model = await svc.get_task_read_model("nonexistent")
    assert model is None


async def test_update_task_read_model_nonexistent_task(svc: ObservabilityService) -> None:
    await svc.update_task_read_model("nonexistent")
    model = await svc.get_task_read_model("nonexistent")
    assert model is None


async def test_list_task_read_models(svc: ObservabilityService, db_path: str) -> None:
    await _insert_task(db_path, "t1", company_id="comp-A")
    await _insert_task(db_path, "t2", company_id="comp-A", status="running")
    await _insert_task(db_path, "t3", company_id="comp-B")
    for tid in ("t1", "t2", "t3"):
        await svc.update_task_read_model(tid)

    all_a = await svc.list_task_read_models("comp-A")
    assert len(all_a) == 2

    running = await svc.list_task_read_models("comp-A", status="running")
    assert len(running) == 1
    assert running[0].task_id == "t2"


async def test_progress_running_with_nodes(svc: ObservabilityService, db_path: str) -> None:
    await _insert_task(db_path, "task-1", status="running")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO task_nodes (node_id, task_id, company_id, node_type, status) VALUES (?, ?, ?, ?, ?)",
            ("n1", "task-1", "comp-1", "agent_step", "completed"),
        )
        await db.execute(
            "INSERT INTO task_nodes (node_id, task_id, company_id, node_type, status) VALUES (?, ?, ?, ?, ?)",
            ("n2", "task-1", "comp-1", "agent_step", "pending"),
        )
        await db.commit()
    await svc.update_task_read_model("task-1")
    model = await svc.get_task_read_model("task-1")
    assert model is not None
    assert model.progress_pct == pytest.approx(50.0)


# ── DashboardMetric ──


async def test_record_and_get_metrics(svc: ObservabilityService) -> None:
    metric = DashboardMetric(
        company_id="comp-1",
        metric_type="throughput",
        metric_name="tasks_per_hour",
        metric_value=42.5,
        period_start="2026-01-01",
        period_end="2026-01-31",
    )
    await svc.record_metric(metric)
    assert metric.metric_id.startswith("dm-")

    metrics = await svc.get_dashboard_metrics("comp-1")
    assert len(metrics) == 1
    assert metrics[0].metric_name == "tasks_per_hour"


async def test_get_metrics_filter_type(svc: ObservabilityService) -> None:
    await svc.record_metric(
        DashboardMetric(
            company_id="comp-1",
            metric_type="throughput",
            metric_name="m1",
            metric_value=1.0,
            period_start="2026-01-01",
            period_end="2026-01-31",
        )
    )
    await svc.record_metric(
        DashboardMetric(
            company_id="comp-1",
            metric_type="latency",
            metric_name="m2",
            metric_value=2.0,
            period_start="2026-01-01",
            period_end="2026-01-31",
        )
    )
    throughput = await svc.get_dashboard_metrics("comp-1", metric_type="throughput")
    assert len(throughput) == 1
    assert throughput[0].metric_type == "throughput"

    all_m = await svc.get_dashboard_metrics("comp-1")
    assert len(all_m) == 2


async def test_get_metrics_empty(svc: ObservabilityService) -> None:
    metrics = await svc.get_dashboard_metrics("comp-empty")
    assert len(metrics) == 0
