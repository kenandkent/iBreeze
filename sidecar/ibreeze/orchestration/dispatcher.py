"""Dispatch approved company plans into department_tasks, employee_tasks, and queued runs.

Called after confirm_plan() sets company_tasks.status = 'approved'.
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


async def dispatch_company_task(
    db: Any,
    company_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Dispatch an approved plan: parse canonical_json, create tasks, enqueue runs."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        task_row = await (await db.execute(
            """SELECT id, status, company_conversation_id
               FROM company_tasks WHERE id=? AND company_id=?""",
            (task_id, company_id),
        )).fetchone()
        if task_row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if task_row["status"] not in ("approved", "dispatching"):
            raise ValueError("STATE_TRANSITION_INVALID")

        plan_row = await (await db.execute(
            """SELECT id, canonical_json FROM company_plan_versions
               WHERE company_task_id=? AND company_id=? AND status='approved'""",
            (task_id, company_id),
        )).fetchone()
        if plan_row is None:
            raise ValueError("NO_APPROVED_PLAN")

        plan = json.loads(plan_row["canonical_json"])
        dept_tasks = plan.get("department_tasks", [])

        created_dept_tasks: list[str] = []
        created_emp_tasks: list[str] = []
        local_ref_to_dept_task: dict[str, str] = {}

        # Create department_tasks
        for dt in dept_tasks:
            dept_task_id = _id()
            local_ref = dt.get("local_ref", "")
            department_id = dt.get("department_id", "")
            objective = dt.get("objective", "")
            deps = dt.get("dependency_refs", [])

            # Check if there are unresolved upstream dependencies
            has_upstream = any(d in local_ref_to_dept_task for d in deps)
            initial_status = "ready" if not has_upstream else "waiting_dependency"

            await db.execute(
                """INSERT INTO department_tasks
                   (id, company_id, company_task_id, department_id, stage_key,
                    objective, deliverables_json, acceptance_criteria_json,
                    status, created_at, updated_at, version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dept_task_id,
                    company_id,
                    task_id,
                    department_id,
                    local_ref,
                    objective,
                    json.dumps(dt.get("deliverables", [])),
                    json.dumps(dt.get("acceptance_criteria", [])),
                    initial_status,
                    now,
                    now,
                    1,
                ),
            )
            created_dept_tasks.append(dept_task_id)
            local_ref_to_dept_task[local_ref] = dept_task_id

            # Create dependencies
            for dep_ref in deps:
                dep_dept_task_id = local_ref_to_dept_task.get(dep_ref)
                if dep_dept_task_id:
                    await db.execute(
                        """INSERT OR IGNORE INTO department_task_dependencies
                           (company_id, company_task_id, department_task_id, depends_on_task_id)
                           VALUES (?,?,?,?)""",
                        (company_id, task_id, dept_task_id, dep_dept_task_id),
                    )

            # Create employee_tasks for this department task
            deliverables = dt.get("deliverables", [])
            for deliv in deliverables:
                contributor_ids = deliv.get("contributor_employee_ids", [])
                for emp_id in contributor_ids:
                    emp_task_id = _id()
                    await db.execute(
                        """INSERT INTO employee_tasks
                           (id, company_id, department_task_id, employee_id,
                            task_kind, objective, acceptance_criteria_json,
                            status, created_at, updated_at, version)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            emp_task_id,
                            company_id,
                            dept_task_id,
                            emp_id,
                            "standard",
                            objective,
                            json.dumps(dt.get("acceptance_criteria", [])),
                            "assigned" if initial_status == "ready" else "waiting_resource",
                            now,
                            now,
                            1,
                        ),
                    )
                    created_emp_tasks.append(emp_task_id)

                    # Enqueue run for this employee task
                    employee_row = await (await db.execute(
                        """SELECT base_profile_version_id FROM employees
                           WHERE id=? AND company_id=?""",
                        (emp_id, company_id),
                    )).fetchone()
                    if employee_row:
                        profile_version_id = employee_row["base_profile_version_id"]
                        profile_row = await (await db.execute(
                            """SELECT profile_type, runtime_binding_json
                               FROM employee_base_profile_versions
                               WHERE id=?""",
                            (profile_version_id,),
                        )).fetchone()
                        if profile_row:
                            binding = json.loads(profile_row["runtime_binding_json"])
                            raw_type = profile_row["profile_type"]
                            adapter_type = raw_type if raw_type in ("api_model", "codex_cli", "claude_code", "opencode") else "codex_cli"
                            model_id = binding.get("agent_cli") or binding.get("api_model", "") or binding.get("claude_code", "") or binding.get("opencode", "")

                            run_id = _id()
                            job_id = _id()
                            run_spec = {
                                "prompt": objective,
                                "model_id": model_id,
                                "run_purpose": "task_execution",
                                "adapter_type": adapter_type,
                            }
                            spec_json = json.dumps(run_spec, sort_keys=True, separators=(",", ":"))
                            spec_sha = hashlib.sha256(spec_json.encode()).hexdigest()

                            await db.execute(
                                """INSERT INTO agent_runs
                                   (id, company_id, company_task_id, department_task_id,
                                    employee_task_id, work_item_id, employee_id,
                                    conversation_id,
                                    availability_snapshot_id, execution_snapshot_id,
                                    run_purpose, adapter_type, run_spec_json,
                                    run_spec_sha256, status, attempt, created_at,
                                    updated_at, version)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    run_id, company_id, task_id, dept_task_id,
                                    emp_task_id, emp_task_id, emp_id,
                                    task_row["company_conversation_id"],
                                    "snap_" + _id(), "snap_" + _id(),
                                    "task_execution", adapter_type,
                                    spec_json, spec_sha,
                                    "queued", 1, now, now, 1,
                                ),
                            )
                            await db.execute(
                                """INSERT INTO runtime_queue
                                   (id, company_id, work_item_type, work_item_id,
                                    job_id, run_id, priority, status, queued_at)
                                   VALUES (?,?, 'employee_task', ?, ?, ?, 0, 'ready', ?)""",
                                (_id(), company_id, emp_task_id, job_id, run_id, now),
                            )

        # Update company task status
        await db.execute(
            """UPDATE company_tasks
               SET status='executing', updated_at=?, version=version+1
               WHERE id=? AND company_id=? AND status IN ('approved','dispatching')""",
            (now, task_id, company_id),
        )

        await db.commit()
        return {
            "task_id": task_id,
            "status": "executing",
            "department_tasks_created": len(created_dept_tasks),
            "employee_tasks_created": len(created_emp_tasks),
        }
    except Exception:
        await db.rollback()
        raise
