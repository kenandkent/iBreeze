"""Runtime agent execution monitoring and control service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ibreeze.runtime.process_supervisor import get_supervisor
from ibreeze.runtime.transport import cancel_model_run, get_reverse_rpc_session


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
    provider_type: str,
) -> dict[str, object]:
    """Check whether a published API/CLI base profile is available.

    The public contract calls this selector ``provider_type``.  Accepting a
    profile UUID as well keeps existing callers compatible while the query
    still enforces company scope and a published current version.
    """
    cursor = await db.execute(
        """SELECT p.id FROM employee_base_profiles p
           JOIN employee_base_profile_versions v ON v.id=p.current_version_id
           WHERE p.company_id = ? AND p.status = 'active' AND v.status='published'
             AND (p.id = ? OR v.profile_type = ?)""",
        (company_id, provider_type, provider_type),
    )
    profile = await cursor.fetchone()
    return {"provider_type": provider_type, "available": profile is not None}


async def list_available_models(
    db: Any,
    company_id: str,
) -> list[dict[str, object]]:
    """List all available models with status."""
    cursor = await db.execute(
        """SELECT p.id AS profile_id, p.name, v.profile_type,
                  v.runtime_binding_json
           FROM employee_base_profiles p
           JOIN employee_base_profile_versions v ON v.id = p.current_version_id
           WHERE p.company_id = ? AND p.status = 'active'
             AND v.status = 'published'""",
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
    limit: int = 50,
) -> list[dict[str, object]]:
    """List agent runs with optional filters."""
    if not 1 <= limit <= 100:
        raise ValueError("LIMIT_INVALID")
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
            ORDER BY created_at DESC, id DESC LIMIT ?""",
        (*params, limit),
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

    run = await _one(
        await db.execute(
            """SELECT status, adapter_type, version FROM agent_runs
               WHERE id=? AND company_id=?""",
            (run_id, company_id),
        )
    )
    if run is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    terminal = {"succeeded", "cancelled", "timed_out", "failed", "lost"}
    if run["status"] in terminal:
        raise ValueError("STATE_TRANSITION_INVALID")

    try:
        adapter_type = run["adapter_type"]
    except (IndexError, KeyError):
        adapter_type = None
    if run["status"] in {"running", "probing", "starting"} and adapter_type == "api_model":
        try:
            await cancel_model_run(run_id, "cancelled by user")
        except Exception as exc:
            raise ValueError("MODEL_CANCEL_FAILED") from exc
    elif run["status"] in {"running", "probing", "starting"} and get_reverse_rpc_session() is not None:
        try:
            await get_supervisor().kill(run_id, reason="cancelled by user")
        except Exception as exc:
            if "RESOURCE_NOT_FOUND" not in str(exc):
                raise ValueError("PROCESS_CANCEL_FAILED") from exc

    cursor = await db.execute(
        """UPDATE agent_runs
           SET status='cancelled', updated_at=?, version=version+1
           WHERE id=? AND company_id=?
           AND status NOT IN ('succeeded','cancelled','timed_out','failed','lost')
           AND version=?""",
        (now, run_id, company_id, int(run["version"])),
    )
    if cursor.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

    await db.execute(
        """UPDATE runtime_queue
           SET status='cancelled'
           WHERE run_id=? AND company_id=?""",
        (run_id, company_id),
    )

    event_id = _id()
    payload = {
        "company_id": company_id,
        "aggregate_id": run_id,
        "version": int(run["version"]) + 1,
        "from_state": run["status"],
        "to_state": "cancelled",
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    await db.execute(
        """INSERT INTO agent_run_events
           (event_id, run_id, event_type, payload_json, sequence, trace_id, occurred_at)
           VALUES (?,?,?,?,COALESCE((SELECT MAX(sequence)+1 FROM agent_run_events WHERE run_id=?),1),?,?)""",
        (event_id, run_id, "run.cancelled", payload_json, run_id, _id(), now),
    )
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            company_id,
            "agent_run",
            run_id,
            int(run["version"]) + 1,
            "run.cancelled",
            payload_json,
            _id(),
            now,
        ),
    )
    await db.execute(
        """INSERT INTO outbox_events
           (id, domain_event_id, topic, payload_json, status, attempts,
            next_attempt_at, created_at)
           VALUES (?,?,?,?,'pending',0,?,?)""",
        (_id(), event_id, "run.cancelled", payload_json, now, now),
    )

    return {
        "run_id": run_id,
        "status": "cancelled",
    }


async def resume_run(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, object]:
    """Resume a paused/waiting run."""
    from ibreeze.state_machine import transition

    now = _now()

    run = await _one(
        await db.execute(
            """SELECT status, resume_state, run_purpose, work_item_id, version, attempt
               FROM agent_runs
               WHERE id=? AND company_id=?""",
            (run_id, company_id),
        )
    )
    if run is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    if run["status"] not in ("waiting_approval", "waiting_resource"):
        raise ValueError("STATE_TRANSITION_INVALID")

    resume_to = run["resume_state"] or "running"
    transition("AgentRun", run["status"], "running")
    if int(run["attempt"]) >= 6:
        raise ValueError("RUN_ATTEMPT_LIMIT_EXCEEDED")

    cursor = await db.execute(
        """UPDATE agent_runs
           SET status='running', resume_state=NULL, attempt=attempt+1,
               updated_at=?, version=version+1
           WHERE id=? AND company_id=?
           AND status IN ('waiting_approval','waiting_resource') AND version=?""",
        (now, run_id, company_id, int(run["version"])),
    )
    if cursor.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

    queue_type = str(run["run_purpose"])
    if queue_type == "task_execution":
        queue_type = "employee_task"
    if queue_type not in {
        "interactive_turn", "company_plan", "employee_task", "review",
        "verification", "repair", "merge", "summary",
    }:
        queue_type = "employee_task"
    await db.execute(
        """INSERT INTO runtime_queue
           (id, company_id, work_item_type, work_item_id, job_id, run_id,
            priority, status, queued_at)
           VALUES (?,?,?,?,?,?,0,'ready',?)""",
        (_id(), company_id, queue_type, run["work_item_id"], _id(), run_id, now),
    )
    event_id = _id()
    payload = {
        "company_id": company_id,
        "aggregate_id": run_id,
        "version": int(run["version"]) + 1,
        "from_state": run["status"],
        "to_state": "running",
        "resume_state": resume_to,
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    await db.execute(
        """INSERT INTO agent_run_events
           (event_id, run_id, event_type, payload_json, sequence, trace_id, occurred_at)
           VALUES (?,?,?,?,COALESCE((SELECT MAX(sequence)+1 FROM agent_run_events WHERE run_id=?),1),?,?)""",
        (event_id, run_id, "run.started", payload_json, run_id, _id(), now),
    )
    return {
        "run_id": run_id,
        "status": "running",
    }
