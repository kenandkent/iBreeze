"""可观测性服务：任务读模型、仪表板指标。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.observability.models import DashboardMetric, TaskReadModel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_task_read_model(row: aiosqlite.Row) -> TaskReadModel:
    return TaskReadModel(
        task_id=row["task_id"],
        company_id=row["company_id"],
        title=row["title"],
        status=row["status"],
        priority=row["priority"],
        assigned_employee_id=row["assigned_employee_id"],
        assigned_backend_id=row["assigned_backend_id"],
        progress_pct=row["progress_pct"],
    )


def _row_to_metric(row: aiosqlite.Row) -> DashboardMetric:
    return DashboardMetric(
        metric_id=row["metric_id"],
        company_id=row["company_id"],
        metric_type=row["metric_type"],
        metric_name=row["metric_name"],
        metric_value=row["metric_value"],
        period_start=row["period_start"],
        period_end=row["period_end"],
    )


class ObservabilityService:
    """可观测性服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def update_task_read_model(self, task_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            )
            task_row = await cursor.fetchone()

            if task_row is None:
                return

            assigned_employee_id: Optional[str] = None
            assign_cursor = await db.execute(
                """SELECT employee_id FROM task_assignments
                   WHERE task_id = ? AND status = 'active' LIMIT 1""",
                (task_id,),
            )
            assign_row = await assign_cursor.fetchone()
            if assign_row:
                assigned_employee_id = assign_row["employee_id"]

            progress_pct = 0.0
            if task_row["status"] == "completed":
                progress_pct = 100.0
            elif task_row["status"] == "running":
                node_cursor = await db.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as done
                       FROM task_nodes WHERE task_id = ?""",
                    (task_id,),
                )
                node_row = await node_cursor.fetchone()
                if node_row and node_row["total"] > 0:
                    progress_pct = (node_row["done"] / node_row["total"]) * 100.0

            now = _now()
            await db.execute(
                """INSERT INTO task_read_model
                   (task_id, company_id, title, status, priority,
                    assigned_employee_id, assigned_backend_id, progress_pct,
                    last_updated_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                    company_id = excluded.company_id,
                    title = excluded.title,
                    status = excluded.status,
                    priority = excluded.priority,
                    assigned_employee_id = excluded.assigned_employee_id,
                    assigned_backend_id = excluded.assigned_backend_id,
                    progress_pct = excluded.progress_pct,
                    last_updated_at = excluded.last_updated_at""",
                (
                    task_id,
                    task_row["company_id"],
                    task_row["title"],
                    task_row["status"],
                    task_row["priority"],
                    assigned_employee_id,
                    task_row["assigned_backend_id"],
                    progress_pct,
                    now,
                    now,
                ),
            )
            await db.commit()

    async def get_task_read_model(self, task_id: str) -> Optional[TaskReadModel]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_read_model WHERE task_id = ?", (task_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_task_read_model(row)

    async def list_task_read_models(
        self, company_id: str, status: Optional[str] = None
    ) -> list[TaskReadModel]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cursor = await db.execute(
                    """SELECT * FROM task_read_model
                       WHERE company_id = ? AND status = ?
                       ORDER BY last_updated_at DESC""",
                    (company_id, status),
                )
            else:
                cursor = await db.execute(
                    """SELECT * FROM task_read_model
                       WHERE company_id = ?
                       ORDER BY last_updated_at DESC""",
                    (company_id,),
                )
            rows = await cursor.fetchall()
            return [_row_to_task_read_model(r) for r in rows]

    async def record_metric(self, metric: DashboardMetric) -> None:
        if not metric.metric_id:
            metric.metric_id = f"dm-{uuid.uuid4().hex[:8]}"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO dashboard_metrics
                   (metric_id, company_id, metric_type, metric_name,
                    metric_value, period_start, period_end, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    metric.metric_id,
                    metric.company_id,
                    metric.metric_type,
                    metric.metric_name,
                    metric.metric_value,
                    metric.period_start,
                    metric.period_end,
                    _now(),
                ),
            )
            await db.commit()

    async def get_dashboard_metrics(
        self, company_id: str, metric_type: Optional[str] = None
    ) -> list[DashboardMetric]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if metric_type:
                cursor = await db.execute(
                    """SELECT * FROM dashboard_metrics
                       WHERE company_id = ? AND metric_type = ?
                       ORDER BY recorded_at DESC""",
                    (company_id, metric_type),
                )
            else:
                cursor = await db.execute(
                    """SELECT * FROM dashboard_metrics
                       WHERE company_id = ?
                       ORDER BY recorded_at DESC""",
                    (company_id,),
                )
            rows = await cursor.fetchall()
            return [_row_to_metric(r) for r in rows]
