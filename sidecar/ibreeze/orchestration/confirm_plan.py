"""Atomic plan confirmation with resource snapshots and dispatch.

Single WriteQueue transaction: validate → snapshot → dispatch → event.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass(frozen=True)
class ConfirmPlanCommand:
    company_id: str
    company_task_id: str
    plan_artifact_id: str
    plan_sha256: str
    expected_version: int
    workspace_grant_ids: Sequence[str] = field(default_factory=list)


class ConfirmPlanResult:
    status: str
    company_task_version: int


async def _run_availability_checks(db: Any, company_id: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    overall = "available"
    cursor = await db.execute("SELECT 1")
    row = await cursor.fetchone()
    checks.append({
        "check": "db_health",
        "status": "available" if row else "unavailable",
        "detail": "",
    })
    cursor = await db.execute(
        "SELECT release_id, downloaded_at FROM catalog_cache_releases"
        " WHERE status='active' ORDER BY downloaded_at DESC LIMIT 1",
    )
    row = await cursor.fetchone()
    if row is None:
        checks.append({
            "check": "catalog_release",
            "status": "unavailable",
            "detail": "No active catalog release",
        })
        overall = "unavailable"
    else:
        checks.append({
            "check": "catalog_release",
            "status": "available",
            "detail": row["release_id"],
        })
    return {"checks": checks, "overall": overall}


async def _ensure_catalog_release(db: Any, now: str) -> str:
    cursor = await db.execute(
        "SELECT release_id FROM catalog_cache_releases WHERE status='active' ORDER BY downloaded_at DESC LIMIT 1",
    )
    row = await cursor.fetchone()
    if row:
        return row["release_id"]  # type: ignore[no-any-return]
    new_id = _id()
    await db.execute(
        "INSERT INTO catalog_cache_releases"
        " (release_id, release_sequence, manifest_json, manifest_sha256,"
        " signature, signing_key_id, status, downloaded_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (new_id, 1, "{}", _sha256("{}"), "auto", "auto", "active", now),
    )
    return new_id


async def _insert_domain_event(
    db: Any,
    event_id: str,
    company_id: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
    payload: dict[str, Any],
    trace_id: str,
    now: str,
) -> None:
    await db.execute(
        "INSERT INTO domain_events (event_id, company_id, aggregate_type,"
        " aggregate_id, aggregate_version, event_type, payload_json,"
        " trace_id, occurred_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            event_id,
            company_id,
            aggregate_type,
            aggregate_id,
            aggregate_version,
            event_type,
            json.dumps(payload, sort_keys=True),
            trace_id,
            now,
        ),
    )


async def _insert_outbox(
    db: Any,
    outbox_id: str,
    domain_event_id: str,
    topic: str,
    payload: dict[str, Any],
    now: str,
) -> None:
    await db.execute(
        "INSERT INTO outbox_events"
        " (id, domain_event_id, topic, payload_json, status, attempts,"
        " next_attempt_at, created_at) VALUES (?,?,?,?,'pending',0,?,?)",
        (outbox_id, domain_event_id, topic, json.dumps(payload, sort_keys=True), now, now),
    )


async def confirm_and_dispatch(
    db: Any,
    command: ConfirmPlanCommand,
) -> dict[str, Any]:
    now = _now()

    cursor = await db.execute(
        "SELECT id, status, version FROM company_tasks WHERE id=? AND company_id=?",
        (command.company_task_id, command.company_id),
    )
    task_row = await cursor.fetchone()
    if task_row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    if task_row["status"] == "executing":
        return {
            "status": "already_confirmed",
            "company_task_version": task_row["version"],
        }
    if task_row["status"] != "awaiting_user_confirmation":
        raise ValueError("STATE_TRANSITION_INVALID")
    if task_row["version"] != command.expected_version:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

    cursor = await db.execute(
        "SELECT id, canonical_json, content_sha256, version_number"
        " FROM company_plan_versions WHERE company_task_id=? AND company_id=?"
        " AND status='awaiting_user_confirmation'"
        " ORDER BY version_number DESC LIMIT 1",
        (command.company_task_id, command.company_id),
    )
    plan_row = await cursor.fetchone()
    if plan_row is None:
        raise ValueError("NO_AWAITING_PLAN")
    if plan_row["content_sha256"] != command.plan_sha256:
        raise ValueError("PLAN_SHA256_MISMATCH")

    plan = json.loads(plan_row["canonical_json"])
    dept_tasks_def = plan.get("department_tasks", [])
    goal = plan.get("goal", "")

    cursor = await db.execute(
        "SELECT id, current_revision_id FROM companies WHERE id=?",
        (command.company_id,),
    )
    company_row = await cursor.fetchone()
    if company_row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    company_revision_id: str = company_row["current_revision_id"] or ""

    cursor = await db.execute(
        "SELECT company_conversation_id FROM company_tasks WHERE id=? AND company_id=?",
        (command.company_task_id, command.company_id),
    )
    conv_row = await cursor.fetchone()
    conversation_id = conv_row["company_conversation_id"] if conv_row else _id()

    catalog_release_id = await _ensure_catalog_release(db, now)

    avail_checks = await _run_availability_checks(db, command.company_id)
    if avail_checks["overall"] == "unavailable":
        return {
            "status": "waiting_resource",
            "company_task_version": command.expected_version,
        }

    created_dept_tasks: list[str] = []
    created_emp_tasks: list[str] = []
    local_ref_to_dept_task: dict[str, str] = {}

    trace_id = _id()

    for dt_def in dept_tasks_def:
        dept_task_id = _id()
        local_ref = dt_def.get("local_ref", "")
        department_id = dt_def.get("department_id", "")
        objective = dt_def.get("objective", "")
        deps = dt_def.get("dependency_refs", [])

        has_upstream = any(d in local_ref_to_dept_task for d in deps)
        initial_status = "ready" if not has_upstream else "waiting_dependency"

        await db.execute(
            "INSERT INTO department_tasks"
            " (id, company_id, company_task_id, department_id, stage_key,"
            " objective, deliverables_json, acceptance_criteria_json,"
            " status, created_at, updated_at, version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                dept_task_id,
                command.company_id,
                command.company_task_id,
                department_id,
                local_ref,
                objective,
                json.dumps(dt_def.get("deliverables", [])),
                json.dumps(dt_def.get("acceptance_criteria", [])),
                initial_status,
                now,
                now,
                1,
            ),
        )
        created_dept_tasks.append(dept_task_id)
        local_ref_to_dept_task[local_ref] = dept_task_id

        for dep_ref in deps:
            dep_dept_task_id = local_ref_to_dept_task.get(dep_ref)
            if dep_dept_task_id:
                await db.execute(
                    "INSERT OR IGNORE INTO department_task_dependencies"
                    " (company_id, company_task_id, department_task_id,"
                    " depends_on_task_id) VALUES (?,?,?,?)",
                    (command.company_id, command.company_task_id, dept_task_id, dep_dept_task_id),
                )

        deliverables = dt_def.get("deliverables", [])
        for deliv in deliverables:
            contributor_ids = deliv.get("contributor_employee_ids", [])
            for emp_id in contributor_ids:
                emp_task_id = _id()
                await db.execute(
                    "INSERT INTO employee_tasks"
                    " (id, company_id, department_task_id, employee_id,"
                    " task_kind, objective, acceptance_criteria_json,"
                    " status, created_at, updated_at, version)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        emp_task_id,
                        command.company_id,
                        dept_task_id,
                        emp_id,
                        "standard",
                        objective,
                        json.dumps(dt_def.get("acceptance_criteria", [])),
                        "assigned" if initial_status == "ready" else "waiting_resource",
                        now,
                        now,
                        1,
                    ),
                )
                created_emp_tasks.append(emp_task_id)

                cursor = await db.execute(
                    "SELECT base_profile_version_id FROM employees WHERE id=? AND company_id=?",
                    (emp_id, command.company_id),
                )
                emp_row = await cursor.fetchone()
                if emp_row is None:
                    continue
                profile_version_id = emp_row["base_profile_version_id"]

                cursor = await db.execute(
                    "SELECT profile_type, runtime_binding_json FROM employee_base_profile_versions WHERE id=?",
                    (profile_version_id,),
                )
                profile_row = await cursor.fetchone()
                if profile_row is None:
                    continue

                binding = json.loads(profile_row["runtime_binding_json"])
                raw_type = profile_row["profile_type"]
                adapter_type = (
                    raw_type
                    if raw_type in ("api_model", "codex_cli", "claude_code", "opencode")
                    else "codex_cli"
                )
                model_id = (
                    binding.get("agent_cli")
                    or binding.get("api_model", "")
                    or binding.get("claude_code", "")
                    or binding.get("opencode", "")
                )

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

                avail_snap_id = _id()
                availability_checks = {"checks": [], "overall": "pending"}
                await db.execute(
                    "INSERT INTO employee_availability_snapshots"
                    " (id, company_id, company_task_id, department_task_id,"
                    " work_item_type, work_item_id, employee_id,"
                    " base_profile_version_id, prospective_execution_sha256,"
                    " catalog_release_id, checks_json, overall_status,"
                    " checked_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        avail_snap_id,
                        command.company_id,
                        command.company_task_id,
                        dept_task_id,
                        "task_execution",
                        emp_task_id,
                        emp_id,
                        profile_version_id,
                        spec_sha,
                        catalog_release_id,
                        json.dumps(availability_checks),
                        "available",
                        now,
                        now,
                    ),
                )

                cursor = await db.execute(
                    "SELECT current_revision_id FROM departments WHERE id=? AND company_id=?",
                    (department_id, command.company_id),
                )
                dept_rev_row = await cursor.fetchone()
                dept_revision_id: str = dept_rev_row["current_revision_id"] if dept_rev_row else ""

                exec_snap_id = _id()
                await db.execute(
                    "INSERT INTO execution_snapshots"
                    " (id, company_id, company_task_id, department_id,"
                    " department_task_id, employee_task_id, employee_id,"
                    " snapshot_purpose, work_item_id, company_revision_id,"
                    " department_revision_id, base_profile_version_id,"
                    " catalog_release_id, runtime_binding_json,"
                    " skill_lock_json, tool_policy_json,"
                    " workspace_policy_json, verification_commands_json,"
                    " content_sha256, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        exec_snap_id,
                        command.company_id,
                        command.company_task_id,
                        department_id,
                        dept_task_id,
                        emp_task_id,
                        emp_id,
                        "task_execution",
                        emp_task_id,
                        company_revision_id,
                        dept_revision_id,
                        profile_version_id,
                        catalog_release_id,
                        json.dumps(binding),
                        "{}",
                        "{}",
                        "{}",
                        "[]",
                        spec_sha,
                        now,
                    ),
                )

                await db.execute(
                    "INSERT INTO agent_runs"
                    " (id, company_id, company_task_id, department_task_id,"
                    " employee_task_id, work_item_id, employee_id,"
                    " conversation_id, availability_snapshot_id,"
                    " execution_snapshot_id, run_purpose, adapter_type,"
                    " run_spec_json, run_spec_sha256, status, attempt,"
                    " created_at, updated_at, version)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        command.company_id,
                        command.company_task_id,
                        dept_task_id,
                        emp_task_id,
                        emp_task_id,
                        emp_id,
                        conversation_id,
                        avail_snap_id,
                        exec_snap_id,
                        "task_execution",
                        adapter_type,
                        spec_json,
                        spec_sha,
                        "queued",
                        1,
                        now,
                        now,
                        1,
                    ),
                )
                await db.execute(
                    "INSERT INTO runtime_queue"
                    " (id, company_id, work_item_type, work_item_id, job_id,"
                    " run_id, priority, status, queued_at)"
                    " VALUES (?,?, 'employee_task', ?, ?, ?, 0, 'ready', ?)",
                    (_id(), command.company_id, emp_task_id, job_id, run_id, now),
                )

    plan_artifact_id = command.plan_artifact_id
    plan_artifact_sha = hashlib.sha256(plan_row["canonical_json"].encode()).hexdigest()
    plan_meta = json.dumps({
        "plan_version_id": plan_row["id"],
        "version_number": plan_row["version_number"],
        "goal": goal,
        "company_task_id": command.company_task_id,
    }, sort_keys=True)
    await db.execute(
        "INSERT INTO artifacts"
        " (id, company_id, company_task_id, artifact_type, logical_name,"
        " object_sha256, object_size, media_type, metadata_json,"
        " created_by_type, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            plan_artifact_id,
            command.company_id,
            command.company_task_id,
            "manifest",
            "company-plan",
            plan_artifact_sha,
            len(plan_row["canonical_json"].encode()),
            "application/json",
            plan_meta,
            "user",
            now,
        ),
    )

    new_version = task_row["version"] + 1
    cursor = await db.execute(
        "UPDATE company_tasks SET status='executing', version=version+1,"
        " updated_at=? WHERE id=? AND company_id=? AND version=?",
        (now, command.company_task_id, command.company_id, command.expected_version),
    )
    if cursor.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

    company_event_id = _id()
    await _insert_domain_event(
        db,
        company_event_id,
        command.company_id,
        "company_task",
        command.company_task_id,
        new_version,
        "company_task.confirmed",
        {
            "company_task_id": command.company_task_id,
            "plan_artifact_id": plan_artifact_id,
            "plan_sha256": command.plan_sha256,
            "new_version": new_version,
            "department_tasks_created": len(created_dept_tasks),
        },
        trace_id,
        now,
    )
    await _insert_outbox(
        db,
        _id(),
        company_event_id,
        "company.task.confirmed",
        {"company_task_id": command.company_task_id},
        now,
    )

    return {
        "status": "confirmed",
        "company_task_version": new_version,
    }
