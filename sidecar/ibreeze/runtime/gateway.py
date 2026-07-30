"""Agent Run gateway — the main entry point for starting, cancelling, and resuming agent runs.

I.1 四个入口：start / cancel / resume / get_status
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class RunValidationError(ValueError):
    pass


class RunNotFoundError(ValueError):
    pass


async def start(
    db: Any,
    *,
    company_id: str,
    company_task_id: str,
    employee_id: str,
    model_id: str,
    prompt: str,
    run_purpose: str,
    adapter_type: str,
    conversation_id: str,
    availability_snapshot_id: str,
    execution_snapshot_id: str,
    work_item_id: str | None = None,
    department_task_id: str | None = None,
    employee_task_id: str | None = None,
) -> dict[str, Any]:
    """Start a new agent run. Validates prerequisites and enqueues."""
    now = _now()

    # Validate company_task exists
    cursor = await db.execute(
        "SELECT id FROM company_tasks WHERE id = ? AND company_id = ?",
        (company_task_id, company_id),
    )
    task = await cursor.fetchone()
    if not task:
        raise RunNotFoundError(f"CompanyTask {company_task_id} not found")

    # Validate employee exists
    cursor = await db.execute(
        "SELECT id FROM employees WHERE id = ? AND company_id = ?",
        (employee_id, company_id),
    )
    agent = await cursor.fetchone()
    if not agent:
        raise RunNotFoundError(f"Employee {employee_id} not found")

    run_id = _id()
    job_id = _id()
    spec = {
        "prompt": prompt,
        "model_id": model_id,
        "run_purpose": run_purpose,
        "adapter_type": adapter_type,
    }
    spec_json = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    spec_sha256 = hashlib.sha256(spec_json.encode()).hexdigest()

    effective_work_item = work_item_id or company_task_id

    valid_work_item_types = {
        "interactive_turn",
        "company_plan",
        "employee_task",
        "review",
        "verification",
        "repair",
        "merge",
        "summary",
    }
    work_item_type = run_purpose if run_purpose in valid_work_item_types else "employee_task"

    # Create agent run record
    await db.execute(
        """INSERT INTO agent_runs
        (id, company_id, company_task_id, department_task_id, employee_task_id,
         work_item_id, employee_id, conversation_id, availability_snapshot_id,
         execution_snapshot_id, run_purpose, adapter_type, native_session_id,
         process_pid, process_group_id, process_started_at, run_spec_json,
         run_spec_sha256, status, resume_state, attempt, started_at,
         completed_at, exit_code, failure_code, created_at, updated_at, version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL,
                NULL, NULL, NULL, ?, ?, 'queued', NULL, 1, NULL,
                NULL, NULL, NULL, ?, ?, 1)""",
        (
            run_id,
            company_id,
            company_task_id,
            department_task_id,
            employee_task_id,
            effective_work_item,
            employee_id,
            conversation_id,
            availability_snapshot_id,
            execution_snapshot_id,
            run_purpose,
            adapter_type,
            spec_json,
            spec_sha256,
            now,
            now,
        ),
    )

    # Enqueue to runtime queue
    await db.execute(
        """INSERT INTO runtime_queue
        (id, company_id, work_item_type, work_item_id, job_id, run_id,
         priority, status, queued_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, 'ready', ?)""",
        (
            _id(),
            company_id,
            work_item_type,
            effective_work_item,
            job_id,
            run_id,
            now,
        ),
    )

    return {"run_id": run_id, "status": "queued", "created_at": now}


async def cancel(
    db: Any,
    company_id: str,
    run_id: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    """Cancel a running agent run."""
    now = _now()

    cursor = await db.execute(
        "SELECT id, status, version FROM agent_runs WHERE id = ? AND company_id = ?",
        (run_id, company_id),
    )
    run = await cursor.fetchone()
    if not run:
        raise RunNotFoundError(f"Run {run_id} not found")

    terminal = {"succeeded", "cancelled", "timed_out", "failed", "lost"}
    if run["status"] in terminal:
        return {"run_id": run_id, "status": run["status"], "message": "Run already terminal"}

    cursor = await db.execute(
        """UPDATE agent_runs
        SET status = 'cancelled', updated_at = ?, version = version + 1
        WHERE id = ? AND company_id = ?
        AND status NOT IN ('succeeded','cancelled','timed_out','failed','lost')""",
        (now, run_id, company_id),
    )
    if cursor.rowcount != 1:
        raise RunValidationError("OPTIMISTIC_LOCK_CONFLICT")

    await db.execute(
        """UPDATE runtime_queue
        SET status = 'cancelled'
        WHERE run_id = ? AND company_id = ?""",
        (run_id, company_id),
    )

    return {"run_id": run_id, "status": "cancelled", "reason": reason}


async def resume(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Resume a paused/waiting agent run."""
    now = _now()

    cursor = await db.execute(
        "SELECT status, resume_state, version FROM agent_runs WHERE id = ? AND company_id = ?",
        (run_id, company_id),
    )
    run = await cursor.fetchone()
    if not run:
        raise RunNotFoundError(f"Run {run_id} not found")

    if run["status"] not in ("waiting_approval", "waiting_resource"):
        raise RunValidationError("STATE_TRANSITION_INVALID")

    resume_to = run["resume_state"] or "running"

    cursor = await db.execute(
        """UPDATE agent_runs
        SET status = ?, resume_state = NULL, updated_at = ?, version = version + 1
        WHERE id = ? AND company_id = ?
        AND status IN ('waiting_approval','waiting_resource')""",
        (resume_to, now, run_id, company_id),
    )
    if cursor.rowcount != 1:
        raise RunValidationError("OPTIMISTIC_LOCK_CONFLICT")

    return {"run_id": run_id, "status": resume_to, "resumed_at": now}


async def get_status(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Get current status of an agent run."""
    cursor = await db.execute(
        "SELECT * FROM agent_runs WHERE id = ? AND company_id = ?",
        (run_id, company_id),
    )
    run = await cursor.fetchone()
    if not run:
        raise RunNotFoundError(f"Run {run_id} not found")
    return dict(run)
