"""Execution trigger chain — handles user confirmation and plan execution flow."""

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


async def request_plan_confirmation(
    db: Any,
    *,
    company_id: str,
    task_id: str,
    plan_version_id: str,
    employee_id: str,
) -> dict[str, Any]:
    """Request user confirmation for a company plan."""
    cursor = await db.execute(
        """SELECT id, status FROM company_plan_versions
           WHERE id = ? AND company_id = ? AND company_task_id = ?""",
        (plan_version_id, company_id, task_id),
    )
    plan = await cursor.fetchone()
    if not plan:
        raise ValueError("PLAN_NOT_FOUND")

    if dict(plan)["status"] != "draft":
        raise ValueError("PLAN_NOT_CONFIRMABLE")

    target_json = json.dumps(
        {"plan_version_id": plan_version_id}, ensure_ascii=False,
    )
    target_sha256 = hashlib.sha256(target_json.encode()).hexdigest()
    now = _now()

    # Find an existing active run for this task to link the approval
    cursor = await db.execute(
        """SELECT id FROM agent_runs
           WHERE company_id = ? AND company_task_id = ? AND run_purpose = 'company_plan'
           ORDER BY created_at DESC LIMIT 1""",
        (company_id, task_id),
    )
    run_row = await cursor.fetchone()
    run_id = dict(run_row)["id"] if run_row else task_id

    approval_id = _id()
    await db.execute(
        """INSERT INTO human_approvals
           (id, company_id, run_id, approval_type, target_json, target_sha256,
            status, requested_at, expires_at, version)
           VALUES (?, ?, ?, 'external_write', ?, ?, 'pending', ?, ?, 1)""",
        (approval_id, company_id, run_id, target_json, target_sha256, now, now),
    )
    await db.commit()

    return {
        "approval_id": approval_id,
        "plan_version_id": plan_version_id,
        "status": "pending",
        "requested_at": now,
    }


async def confirm_plan(
    db: Any,
    *,
    company_id: str,
    approval_id: str,
    employee_id: str,
    decision: str = "approved",
) -> dict[str, Any]:
    """User confirms or rejects a plan."""
    now = _now()

    # Resolve the approval
    new_status = "allowed" if decision == "approved" else "denied"
    await db.execute(
        """UPDATE human_approvals
           SET status = ?, resolved_at = ?
           WHERE id = ? AND company_id = ?""",
        (new_status, now, approval_id, company_id),
    )

    # Extract plan_version_id from the approval target
    cursor = await db.execute(
        "SELECT target_json FROM human_approvals WHERE id = ?",
        (approval_id,),
    )
    approval = await cursor.fetchone()
    if approval:
        target = json.loads(dict(approval)["target_json"])
        plan_version_id = target.get("plan_version_id", "")
        plan_status = "confirmed" if decision == "approved" else "rejected"
        await db.execute(
            """UPDATE company_plan_versions
               SET status = ?, confirmed_at = ?
               WHERE id = ? AND company_id = ?""",
            (plan_status, now, plan_version_id, company_id),
        )

    await db.commit()

    return {
        "approval_id": approval_id,
        "decision": decision,
        "resolved_at": now,
    }


async def modify_plan(
    db: Any,
    *,
    company_id: str,
    plan_version_id: str,
    modifications: dict[str, Any],
) -> dict[str, Any]:
    """Modify a plan based on user feedback — creates a new version."""
    now = _now()

    cursor = await db.execute(
        """SELECT id, company_task_id, version_number, canonical_json, generated_by_run_id
           FROM company_plan_versions
           WHERE id = ? AND company_id = ?""",
        (plan_version_id, company_id),
    )
    plan = await cursor.fetchone()
    if not plan:
        raise ValueError("PLAN_NOT_FOUND")

    plan_row = dict(plan)
    current_content: dict[str, Any] = json.loads(plan_row["canonical_json"])
    current_content.update(modifications)

    new_canonical = json.dumps(current_content, ensure_ascii=False, sort_keys=True)
    new_sha256 = hashlib.sha256(new_canonical.encode()).hexdigest()

    new_version_id = _id()
    new_version_number = plan_row["version_number"] + 1
    await db.execute(
        """INSERT INTO company_plan_versions
           (id, company_task_id, company_id, version_number, canonical_json,
            content_sha256, generated_by_run_id, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
        (
            new_version_id,
            plan_row["company_task_id"],
            company_id,
            new_version_number,
            new_canonical,
            new_sha256,
            plan_row["generated_by_run_id"],
            now,
        ),
    )
    await db.commit()

    return {
        "new_version_id": new_version_id,
        "modified_at": now,
    }
