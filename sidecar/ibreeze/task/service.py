"""Company and department task lifecycle service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())  # pragma: no cover


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def confirm_plan(
    db: Any,
    company_id: str,
    task_id: str,
    employee_id: str,
) -> dict[str, object]:
    """User confirms company plan (awaiting_user_confirmation → approved)."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task = await _one(
            await db.execute(
                """SELECT * FROM company_tasks
                   WHERE id=? AND company_id=?""",
                (task_id, company_id),
            )
        )
        if task is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if task["status"] != "awaiting_user_confirmation":
            raise ValueError("STATE_TRANSITION_INVALID")

        plan = await _one(
            await db.execute(
                """SELECT id FROM company_plan_versions
                   WHERE company_task_id=? AND company_id=?
                   AND status='awaiting_user_confirmation'""",
                (task_id, company_id),
            )
        )
        if plan is None:
            raise ValueError("NO_AWAITING_PLAN")

        await db.execute(
            """UPDATE company_plan_versions
               SET status='approved', confirmed_at=?
               WHERE id=? AND company_id=?""",
            (now, plan["id"], company_id),
        )

        cursor = await db.execute(
            """UPDATE company_tasks
               SET status='approved', updated_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status='awaiting_user_confirmation'""",
            (now, task_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.commit()
        return {
            "task_id": task_id,
            "plan_version_id": plan["id"],
            "status": "approved",
        }
    except Exception:
        await db.rollback()
        raise


async def request_plan_revision(
    db: Any,
    company_id: str,
    task_id: str,
    employee_id: str,
    *,
    reason: str,
) -> dict[str, object]:
    """Request plan revision."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task = await _one(
            await db.execute(
                """SELECT * FROM company_tasks
                   WHERE id=? AND company_id=?""",
                (task_id, company_id),
            )
        )
        if task is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if task["status"] != "awaiting_user_confirmation":
            raise ValueError("STATE_TRANSITION_INVALID")

        plan = await _one(
            await db.execute(
                """SELECT id FROM company_plan_versions
                   WHERE company_task_id=? AND company_id=?
                   AND status='awaiting_user_confirmation'""",
                (task_id, company_id),
            )
        )
        if plan is not None:
            await db.execute(
                """UPDATE company_plan_versions
                   SET status='superseded'
                   WHERE id=? AND company_id=?""",
                (plan["id"], company_id),
            )

        cursor = await db.execute(
            """UPDATE company_tasks
               SET status='revision_requested', updated_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status='awaiting_user_confirmation'""",
            (now, task_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.commit()
        return {
            "task_id": task_id,
            "status": "revision_requested",
            "reason": reason,
        }
    except Exception:  # pragma: no cover
        await db.rollback()
        raise


async def reject_plan(
    db: Any,
    company_id: str,
    task_id: str,
    employee_id: str,
    *,
    reason: str,
) -> dict[str, object]:
    """Reject plan."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task = await _one(
            await db.execute(
                """SELECT * FROM company_tasks
                   WHERE id=? AND company_id=?""",
                (task_id, company_id),
            )
        )
        if task is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if task["status"] != "awaiting_user_confirmation":
            raise ValueError("STATE_TRANSITION_INVALID")

        plan = await _one(
            await db.execute(
                """SELECT id FROM company_plan_versions
                   WHERE company_task_id=? AND company_id=?
                   AND status='awaiting_user_confirmation'""",
                (task_id, company_id),
            )
        )
        if plan is not None:
            await db.execute(
                """UPDATE company_plan_versions
                   SET status='rejected'
                   WHERE id=? AND company_id=?""",
                (plan["id"], company_id),
            )

        cursor = await db.execute(
            """UPDATE company_tasks
               SET status='rejected', updated_at=?, completed_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status='awaiting_user_confirmation'""",
            (now, now, task_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.commit()
        return {
            "task_id": task_id,
            "status": "rejected",
            "reason": reason,
        }
    except Exception:  # pragma: no cover
        await db.rollback()
        raise


async def pause_task(
    db: Any,
    company_id: str,
    task_id: str,
    employee_id: str,
) -> dict[str, object]:
    """Pause a running task (executing, reviewing, or fixing)."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task = await _one(
            await db.execute(
                """SELECT status FROM company_tasks
                   WHERE id=? AND company_id=?""",
                (task_id, company_id),
            )
        )
        if task is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if task["status"] not in ("executing", "reviewing", "fixing"):
            raise ValueError("STATE_TRANSITION_INVALID")

        resume_state = task["status"]
        cursor = await db.execute(
            """UPDATE company_tasks
               SET status='paused', resume_state=?,
                   updated_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status IN ('executing','reviewing','fixing')""",
            (resume_state, now, task_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.commit()
        return {
            "task_id": task_id,
            "status": "paused",
            "resume_state": resume_state,
        }
    except Exception:
        await db.rollback()
        raise


async def resume_task(
    db: Any,
    company_id: str,
    task_id: str,
    employee_id: str,
) -> dict[str, object]:
    """Resume a paused task."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task = await _one(
            await db.execute(
                """SELECT resume_state, status FROM company_tasks
                   WHERE id=? AND company_id=?""",
                (task_id, company_id),
            )
        )
        if task is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if task["status"] != "paused":
            raise ValueError("STATE_TRANSITION_INVALID")

        resume_to = task["resume_state"] or "executing"

        cursor = await db.execute(
            """UPDATE company_tasks
               SET status=?, resume_state=NULL, updated_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status='paused'""",
            (resume_to, now, task_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.commit()
        return {
            "task_id": task_id,
            "status": resume_to,
        }
    except Exception:
        await db.rollback()
        raise


async def cancel_task(
    db: Any,
    company_id: str,
    task_id: str,
    employee_id: str,
    *,
    reason: str,
) -> dict[str, object]:
    """Cancel a task."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task = await _one(
            await db.execute(
                """SELECT status FROM company_tasks
                   WHERE id=? AND company_id=?""",
                (task_id, company_id),
            )
        )
        if task is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        terminal = {"completed", "cancelled", "failed"}
        if task["status"] in terminal:
            raise ValueError("STATE_TRANSITION_INVALID")

        cursor = await db.execute(
            """UPDATE company_tasks
               SET status='cancelling', updated_at=?, version=version+1
               WHERE id=? AND company_id=?
               AND status NOT IN ('completed','cancelled','failed')""",
            (now, task_id, company_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

        await db.commit()
        return {
            "task_id": task_id,
            "status": "cancelling",
            "reason": reason,
        }
    except Exception:
        await db.rollback()
        raise


async def get_company_task(
    db: Any,
    company_id: str,
    task_id: str,
) -> dict[str, object] | None:
    """Get company task details."""
    row = await _one(
        await db.execute(
            "SELECT * FROM company_tasks WHERE id=? AND company_id=?",
            (task_id, company_id),
        )
    )
    return dict(row) if row is not None else None


async def list_company_tasks(
    db: Any,
    company_id: str,
    *,
    status: str | None = None,
) -> list[dict[str, object]]:
    """List company tasks with optional status filter."""
    conditions = ["company_id=?"]
    params: list[Any] = [company_id]

    if status is not None:
        conditions.append("status=?")
        params.append(status)

    where = " AND ".join(conditions)

    cursor = await db.execute(
        f"""SELECT * FROM company_tasks
            WHERE {where}
            ORDER BY created_at DESC, id DESC""",
        tuple(params),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def get_task_graph(
    db: Any,
    company_id: str,
    task_id: str,
) -> dict[str, object]:
    """Get task dependency graph."""
    task = await _one(
        await db.execute(
            "SELECT id, status FROM company_tasks WHERE id=? AND company_id=?",
            (task_id, company_id),
        )
    )
    if task is None:
        raise ValueError("RESOURCE_NOT_FOUND")

    cursor = await db.execute(
        """SELECT dt.id, dt.department_id, dt.status, dt.stage_key
           FROM department_tasks dt
           WHERE dt.company_task_id=? AND dt.company_id=?""",
        (task_id, company_id),
    )
    dept_tasks = [dict(row) for row in await cursor.fetchall()]

    dep_cursor = await db.execute(
        """SELECT department_task_id, depends_on_task_id
           FROM department_task_dependencies
           WHERE company_task_id=? AND company_id=?""",
        (task_id, company_id),
    )
    dependencies = [dict(row) for row in await dep_cursor.fetchall()]

    return {
        "task_id": task_id,
        "status": task["status"],
        "department_tasks": dept_tasks,
        "dependencies": dependencies,
    }


async def get_task_evidence(
    db: Any,
    company_id: str,
    task_id: str,
) -> dict[str, object]:
    """Get task execution evidence (agent runs, artifacts)."""
    runs_cursor = await db.execute(
        """SELECT * FROM agent_runs
           WHERE company_task_id=? AND company_id=?
           ORDER BY created_at DESC""",
        (task_id, company_id),
    )
    runs = [dict(row) for row in await runs_cursor.fetchall()]

    artifacts_cursor = await db.execute(
        """SELECT * FROM artifacts
           WHERE company_task_id=? AND company_id=?
           ORDER BY created_at DESC""",
        (task_id, company_id),
    )
    artifacts = [dict(row) for row in await artifacts_cursor.fetchall()]

    return {
        "task_id": task_id,
        "runs": runs,
        "artifacts": artifacts,
    }


async def check_department_resources(
    db: Any,
    company_id: str,
    dept_task_id: str,
) -> dict[str, object]:
    """Check if department has resources for a task."""
    dept_task = await _one(
        await db.execute(
            """SELECT * FROM department_tasks
               WHERE id=? AND company_id=?""",
            (dept_task_id, company_id),
        )
    )
    if dept_task is None:
        raise ValueError("RESOURCE_NOT_FOUND")

    cursor = await db.execute(
        """SELECT et.employee_id, et.status
           FROM employee_tasks et
           WHERE et.department_task_id=? AND et.company_id=?
           AND et.status NOT IN ('cancelled', 'failed')""",
        (dept_task_id, company_id),
    )
    assigned = [dict(row) for row in await cursor.fetchall()]

    return {
        "department_task_id": dept_task_id,
        "department_id": dept_task["department_id"],
        "status": dept_task["status"],
        "assigned_employees": assigned,
        "has_resources": len(assigned) > 0,
    }


async def replace_employee(
    db: Any,
    company_id: str,
    dept_task_id: str,
    *,
    old_employee_id: str,
    new_employee_id: str,
) -> dict[str, object]:
    """Replace assigned employee on a department task."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task = await _one(
            await db.execute(
                """SELECT * FROM employee_tasks
                   WHERE department_task_id=? AND company_id=?
                   AND employee_id=?""",
                (dept_task_id, company_id, old_employee_id),
            )
        )
        if task is None:
            raise ValueError("RESOURCE_NOT_FOUND")

        new_id = _id()
        await db.execute(
            """INSERT INTO employee_tasks
               (id, company_id, department_task_id, employee_id, task_kind,
                objective, acceptance_criteria_json, status, resume_state,
                created_at, updated_at, version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                new_id,
                company_id,
                dept_task_id,
                new_employee_id,
                task["task_kind"],
                task["objective"],
                task["acceptance_criteria_json"],
                "assigned",
                None,
                now,
                now,
                1,
            ),
        )

        await db.execute(
            """UPDATE employee_tasks
               SET status='cancelled', updated_at=?
               WHERE id=? AND company_id=?""",
            (now, task["id"], company_id),
        )

        await db.commit()
        return {
            "old_employee_id": old_employee_id,
            "new_employee_id": new_employee_id,
            "new_task_id": new_id,
        }
    except Exception:  # pragma: no cover
        await db.rollback()
        raise


async def get_department_task_report(
    db: Any,
    company_id: str,
    dept_task_id: str,
) -> dict[str, object]:
    """Get department task report."""
    dept_task = await _one(
        await db.execute(
            """SELECT * FROM department_tasks
               WHERE id=? AND company_id=?""",
            (dept_task_id, company_id),
        )
    )
    if dept_task is None:
        raise ValueError("RESOURCE_NOT_FOUND")

    emp_cursor = await db.execute(
        """SELECT et.*, e.display_name AS employee_name
           FROM employee_tasks et
           LEFT JOIN employees e ON e.id = et.employee_id AND e.company_id = et.company_id
           WHERE et.department_task_id=? AND et.company_id=?
           ORDER BY et.created_at""",
        (dept_task_id, company_id),
    )
    employee_tasks = [dict(row) for row in await emp_cursor.fetchall()]

    return {
        "department_task_id": dept_task_id,
        "company_task_id": dept_task["company_task_id"],
        "department_id": dept_task["department_id"],
        "status": dept_task["status"],
        "objective": dept_task["objective"],
        "employee_tasks": employee_tasks,
    }
