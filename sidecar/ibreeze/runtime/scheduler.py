"""Fair persistent scheduler for agent run queue.

P5-T04: 公平持久调度器，按公司公平性 + 优先级 + FIFO 排序。
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def enqueue(
    db: Any,
    company_id: str,
    run_id: str,
    *,
    work_item_type: str,
    work_item_id: str,
    job_id: str,
    priority: int = 0,
) -> str:
    """Add a run to the scheduling queue."""
    qid = _id()
    now = _now()
    await db.execute(
        """INSERT INTO runtime_queue
        (id, company_id, work_item_type, work_item_id, job_id, run_id,
         priority, status, queued_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?)""",
        (qid, company_id, work_item_type, work_item_id, job_id, run_id, priority, now),
    )
    return qid


async def dequeue_next(db: Any) -> dict[str, Any] | None:
    """Get the next run to execute, considering fairness.

    排序逻辑：公司已调度次数 ASC → priority ASC → queued_at ASC
    """
    cursor = await db.execute(
        """SELECT q.*, f.last_dispatched_at
        FROM runtime_queue q
        LEFT JOIN runtime_company_fairness f ON f.company_id = q.company_id
        WHERE q.status = 'ready'
        ORDER BY f.last_dispatched_at ASC NULLS FIRST,
                 q.priority ASC,
                 q.queued_at ASC
        LIMIT 1"""
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return dict(row)


async def acquire_lease(
    db: Any,
    *,
    queue_id: str,
    job_id: str,
    run_id: str,
    employee_id: str,
    company_id: str,
    conversation_id: str,
    ttl_seconds: int = 300,
) -> str | None:
    """Acquire an execution lease for a run."""
    now = _now()
    lease_id = _id()

    emp_id = employee_id or None
    conv_id = conversation_id or None
    run_id_val = run_id or None

    queue = await (
        await db.execute(
            "SELECT status, job_id, company_id FROM runtime_queue WHERE id=?",
            (queue_id,),
        )
    ).fetchone()
    if queue is None or queue["status"] != "ready" or queue["job_id"] != job_id or queue["company_id"] != company_id:
        return None
    try:
        await db.execute(
            """INSERT INTO runtime_leases
            (id, queue_id, job_id, run_id, employee_id, company_id,
             conversation_id, acquired_at, heartbeat_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime(?, '+' || ? || ' seconds'))""",
            (
                lease_id,
                queue_id,
                job_id,
                run_id_val,
                emp_id,
                company_id,
                conv_id,
                now,
                now,
                now,
                ttl_seconds,
            ),
        )
    except sqlite3.IntegrityError:
        return None
    cursor = await db.execute(
        "UPDATE runtime_queue SET status = 'leased', leased_at = ? WHERE id = ? AND status='ready'",
        (now, queue_id),
    )
    if cursor.rowcount != 1:
        await db.execute("DELETE FROM runtime_leases WHERE id=?", (lease_id,))
        return None
    return lease_id


async def heartbeat_lease(db: Any, lease_id: str) -> bool:
    """Update lease heartbeat to prevent expiry."""
    now = _now()
    cursor = await db.execute(
        """UPDATE runtime_leases
        SET heartbeat_at = ?
        WHERE id = ? AND expires_at > ?""",
        (now, lease_id, now),
    )
    return cursor.rowcount == 1  # type: ignore[no-any-return]


async def release_lease(db: Any, lease_id: str) -> None:
    """Release a lease and mark queue entry completed."""
    _now()
    cursor = await db.execute(
        "SELECT queue_id FROM runtime_leases WHERE id = ?",
        (lease_id,),
    )
    row = await cursor.fetchone()
    if row:
        await db.execute(
            "UPDATE runtime_queue SET status = 'completed' WHERE id = ?",
            (row["queue_id"],),
        )
    await db.execute("DELETE FROM runtime_leases WHERE id = ?", (lease_id,))


async def update_fairness(db: Any, company_id: str) -> None:
    """Update the last dispatched timestamp for fairness scheduling."""
    now = _now()
    await db.execute(
        """INSERT INTO runtime_company_fairness (company_id, last_dispatched_at)
        VALUES (?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            last_dispatched_at = excluded.last_dispatched_at""",
        (company_id, now),
    )
