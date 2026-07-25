"""Runtime agent execution monitoring and control service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def probe_agent(
    db: Any,
    company_id: str,
    agent_id: str,
) -> dict[str, object]:
    """Check if agent is available (CLI installed, model accessible)."""
    cursor = await db.execute(
        "SELECT id, display_name, status FROM employees WHERE id = ? AND company_id = ?",
        (agent_id, company_id),
    )
    agent = await cursor.fetchone()
    if not agent:
        raise ValueError("AGENT_NOT_FOUND")
    return {
        "agent_id": agent_id,
        "available": dict(agent)["status"] == "active",
        "name": dict(agent)["display_name"],
    }


async def probe_provider(
    db: Any,
    company_id: str,
    provider_id: str,
) -> dict[str, object]:
    """Check if provider is reachable."""
    cursor = await db.execute(
        "SELECT id FROM employee_base_profiles WHERE employee_id = ? AND company_id = ?",
        (provider_id, company_id),
    )
    profile = await cursor.fetchone()
    return {"provider_id": provider_id, "available": profile is not None}


async def list_available_models(
    db: Any,
    company_id: str,
) -> list[dict[str, object]]:
    """List all available models with status."""
    cursor = await db.execute(
        "SELECT employee_id, agent_cli, api_model FROM employee_base_profiles WHERE company_id = ? AND status = 'published'",
        (company_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows] if rows else []


async def get_runtime_status(
    db: Any,
    company_id: str,
) -> dict[str, object]:
    """Get overall runtime status (queue depth, active runs, etc.)."""
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM runtime_queue WHERE company_id = ?",
        (company_id,),
    )
    queue_row = await cursor.fetchone()
    queue_depth = dict(queue_row)["cnt"] if queue_row else 0

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM agent_runs WHERE company_id = ? AND status = 'running'",
        (company_id,),
    )
    active_row = await cursor.fetchone()
    active_runs = dict(active_row)["cnt"] if active_row else 0

    return {"queue_depth": queue_depth, "active_runs": active_runs, "status": "healthy"}


async def list_agent_runs(
    db: Any,
    company_id: str,
    *,
    task_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    """List agent runs with optional filters."""
    conditions = ["company_id=?"]
    params: list[Any] = [company_id]

    if task_id is not None:
        conditions.append("company_task_id=?")
        params.append(task_id)
    if status is not None:
        conditions.append("status=?")
        params.append(status)

    where = " AND ".join(conditions)

    cursor = await db.execute(
        f"""SELECT * FROM agent_runs
            WHERE {where}
            ORDER BY created_at DESC, id DESC""",
        tuple(params),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def get_agent_run(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, object] | None:
    """Get agent run details."""
    row = await _one(
        await db.execute(
            "SELECT * FROM agent_runs WHERE id=? AND company_id=?",
            (run_id, company_id),
        )
    )
    return dict(row) if row is not None else None


async def list_run_events(
    db: Any,
    company_id: str,
    run_id: str,
) -> list[dict[str, object]]:
    """List events for a run."""
    run = await _one(
        await db.execute(
            "SELECT id FROM agent_runs WHERE id=? AND company_id=?",
            (run_id, company_id),
        )
    )
    if run is None:
        raise ValueError("RESOURCE_NOT_FOUND")

    cursor = await db.execute(
        """SELECT * FROM agent_run_events
           WHERE run_id=?
           ORDER BY sequence ASC""",
        (run_id,),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def cancel_run(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, object]:
    """Cancel a running agent."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        run = await _one(
            await db.execute(
                """SELECT status FROM agent_runs
                   WHERE id=? AND company_id=?""",
                (run_id, company_id),
            )
        )
        if run is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        terminal = {"succeeded", "cancelled", "timed_out", "failed", "lost"}
        if run["status"] in terminal:
            raise ValueError("STATE_TRANSITION_INVALID")

        cursor = await db.execute(
            """UPDATE agent_runs
               SET status='cancelled', updated_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status NOT IN ('succeeded','cancelled','timed_out','failed','lost')""",
            (now, run_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.execute(
            """UPDATE runtime_queue
               SET status='cancelled'
               WHERE run_id=? AND company_id=?""",
            (run_id, company_id),
        )

        await db.commit()
        return {
            "run_id": run_id,
            "status": "cancelled",
        }
    except Exception:
        await db.rollback()
        raise


async def resume_run(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, object]:
    """Resume a paused/waiting run."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        run = await _one(
            await db.execute(
                """SELECT status, resume_state FROM agent_runs
                   WHERE id=? AND company_id=?""",
                (run_id, company_id),
            )
        )
        if run is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if run["status"] not in ("waiting_approval", "waiting_resource"):
            raise ValueError("STATE_TRANSITION_INVALID")

        resume_to = run["resume_state"] or "running"

        cursor = await db.execute(
            """UPDATE agent_runs
               SET status=?, resume_state=NULL, updated_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status IN ('waiting_approval','waiting_resource')""",
            (resume_to, now, run_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.commit()
        return {
            "run_id": run_id,
            "status": resume_to,
        }
    except Exception:
        await db.rollback()
        raise
