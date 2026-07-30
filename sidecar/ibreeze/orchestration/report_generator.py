"""Report generation for department tasks and company-level review."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def generate_department_report(
    db: Any,
    *,
    company_id: str,
    department_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Generate a department-level task completion report."""
    cursor = await db.execute(
        """SELECT d.id, dr.name
           FROM departments d
           JOIN department_revisions dr ON dr.id = d.current_revision_id
           WHERE d.id = ? AND d.company_id = ?""",
        (department_id, company_id),
    )
    dept = await cursor.fetchone()

    cursor = await db.execute(
        """SELECT COUNT(*) AS cnt FROM department_tasks
           WHERE department_id = ? AND company_id = ? AND status = 'completed'""",
        (department_id, company_id),
    )
    completed_row = await cursor.fetchone()
    completed_count = dict(completed_row)["cnt"] if completed_row else 0

    cursor = await db.execute(
        """SELECT COUNT(*) AS cnt FROM artifacts
           WHERE company_id = ? AND company_task_id = ? AND department_task_id IN
             (SELECT id FROM department_tasks WHERE department_id = ? AND company_id = ?)""",
        (company_id, task_id, department_id, company_id),
    )
    artifact_row = await cursor.fetchone()
    artifact_count = dict(artifact_row)["cnt"] if artifact_row else 0

    report = {
        "report_type": "department",
        "department_id": department_id,
        "department_name": dict(dept)["name"] if dept else "",
        "completed_task_count": completed_count,
        "artifact_count": artifact_count,
        "generated_at": _now(),
    }

    return report


async def generate_company_review(
    db: Any,
    *,
    company_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Generate a company-level review summary."""
    cursor = await db.execute(
        "SELECT id FROM departments WHERE company_id = ?",
        (company_id,),
    )
    departments = await cursor.fetchall()

    cursor = await db.execute(
        """SELECT status, COUNT(*) AS cnt FROM department_tasks
           WHERE company_id = ? AND company_task_id = ? GROUP BY status""",
        (company_id, task_id),
    )
    status_counts = await cursor.fetchall()

    cursor = await db.execute(
        """SELECT COUNT(*) AS cnt FROM review_assignments
           WHERE company_id = ? AND artifact_id IN
             (SELECT id FROM artifacts WHERE company_id = ? AND company_task_id = ?)""",
        (company_id, company_id, task_id),
    )
    review_row = await cursor.fetchone()
    review_count = dict(review_row)["cnt"] if review_row else 0

    review = {
        "review_type": "company",
        "company_id": company_id,
        "department_count": len(departments) if departments else 0,
        "task_status_summary": ({dict(r)["status"]: dict(r)["cnt"] for r in status_counts} if status_counts else {}),
        "review_count": review_count,
        "generated_at": _now(),
    }

    return review


async def _check_completion_gates(db: Any, *, company_id: str, task_id: str) -> dict[str, Any] | None:
    try:
        cursor = await db.execute(
            """SELECT id, gate_type, status, failed_at, error_message
               FROM completion_gates
               WHERE company_id=? AND (task_id=? OR task_id IS NULL)
               ORDER BY gate_type""",
            (company_id, task_id),
        )
        gates = await cursor.fetchall()
    except Exception:
        return None

    if not gates:
        return None

    blocking = []
    for g in gates:
        gd = dict(g)
        if gd["status"] != "passed":
            blocking.append(gd)

    if blocking:
        return {"gate_blocked": True, "blocking_gates": blocking}
    return None


async def generate_final_report(
    db: Any,
    *,
    company_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Generate the final company task report after all departments complete."""
    blocked = await _check_completion_gates(db, company_id=company_id, task_id=task_id)
    if blocked is not None:
        return blocked

    company_review = await generate_company_review(db, company_id=company_id, task_id=task_id)

    cursor = await db.execute(
        "SELECT id FROM departments WHERE company_id = ?",
        (company_id,),
    )
    departments = await cursor.fetchall()

    dept_reports: list[dict[str, Any]] = []
    for dept in departments:
        dept_id = dict(dept)["id"]
        report = await generate_department_report(
            db,
            company_id=company_id,
            department_id=dept_id,
            task_id=task_id,
        )
        dept_reports.append(report)

    final = {
        "report_type": "final",
        "company_id": company_id,
        "company_summary": company_review,
        "department_reports": dept_reports,
        "generated_at": _now(),
    }

    return final
