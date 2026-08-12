"""Atomic plan confirmation with resource snapshots and dispatch.

Single WriteQueue transaction: validate → snapshot → dispatch → event.

The confirmation path is the only production entry point for turning an
awaiting plan into executable work. It records every CompanyTask state edge
(``approved → dispatching → checking_resources → executing``) in order and
performs a deterministic, per-employee resource preflight before any task or
run row is written.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ibreeze.orchestration.run_builder import RunSpec, build_run


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
    checks.append(
        {
            "check": "db_health",
            "status": "available" if row else "unavailable",
            "detail": "",
        }
    )
    cursor = await db.execute(
        "SELECT release_id, downloaded_at FROM catalog_cache_releases"
        " WHERE status='active' ORDER BY downloaded_at DESC LIMIT 1",
    )
    row = await cursor.fetchone()
    if row is None:
        checks.append(
            {
                "check": "catalog_release",
                "status": "unavailable",
                "detail": "No active catalog release",
            }
        )
        overall = "unavailable"
    else:
        checks.append(
            {
                "check": "catalog_release",
                "status": "available",
                "detail": row["release_id"],
            }
        )
    return {"checks": checks, "overall": overall}


async def _active_catalog_release(db: Any) -> str | None:
    cursor = await db.execute(
        "SELECT release_id FROM catalog_cache_releases WHERE status='active' ORDER BY downloaded_at DESC LIMIT 1",
    )
    row = await cursor.fetchone()
    return str(row["release_id"]) if row else None


async def _prepare_employee_resources(
    db: Any,
    *,
    company_id: str,
    department_tasks: list[dict[str, Any]],
    catalog_release_id: str,
    workspace_grant_id: str,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Resolve and validate every employee used by a plan before dispatch.

    This is deliberately a database-only preflight. It verifies that the
    immutable profile and signed catalog references are internally consistent;
    the Rust supervisor performs the authoritative executable/credential
    probes immediately before a run starts. Returning ``False`` leaves the
    plan in ``awaiting_user_confirmation`` so the caller can retry after the
    missing resource is repaired, without leaving a partial task graph.
    """

    resources: dict[str, dict[str, Any]] = {}
    all_available = True

    for department_task in department_tasks:
        if not isinstance(department_task, dict):
            return {}, False
        department_id = str(department_task.get("department_id", ""))
        department_cursor = await db.execute(
            "SELECT id, status, current_revision_id FROM departments"
            " WHERE id=? AND company_id=?",
            (department_id, company_id),
        )
        department_row = await department_cursor.fetchone()
        if (
            department_row is None
            or department_row["status"] != "active"
            or not department_row["current_revision_id"]
        ):
            all_available = False

        deliverables = department_task.get("deliverables", [])
        if not isinstance(deliverables, list) or not deliverables:
            return {}, False
        for deliverable in deliverables:
            if not isinstance(deliverable, dict):
                return {}, False
            employee_ids = deliverable.get("contributor_employee_ids", [])
            if not isinstance(employee_ids, list) or not employee_ids:
                return {}, False
            for employee_id_value in employee_ids:
                employee_id = str(employee_id_value)
                if employee_id in resources:
                    if resources[employee_id]["department_id"] != department_id:
                        all_available = False
                    continue

                cursor = await db.execute(
                    """SELECT e.id, e.department_id, e.status AS employee_status,
                              e.base_profile_version_id,
                              v.status AS profile_version_status,
                              v.profile_type, v.runtime_binding_json,
                              v.catalog_release_id,
                              p.status AS profile_status
                       FROM employees e
                       LEFT JOIN employee_base_profile_versions v
                         ON v.id=e.base_profile_version_id
                       LEFT JOIN employee_base_profiles p
                         ON p.id=v.profile_id
                       WHERE e.id=? AND e.company_id=?""",
                    (employee_id, company_id),
                )
                row = await cursor.fetchone()
                checks: list[dict[str, str]] = []
                if row is None:
                    resources[employee_id] = {
                        "department_id": department_id,
                        "available": False,
                        "checks": [
                            {
                                "check": "employee",
                                "status": "unavailable",
                                "detail": "EMPLOYEE_NOT_FOUND",
                            }
                        ],
                    }
                    all_available = False
                    continue

                employee_available = True
                employee_status = row["employee_status"] == "active"
                checks.append(
                    {
                        "check": "employee_status",
                        "status": "available" if employee_status else "unavailable",
                        "detail": str(row["employee_status"]),
                    }
                )
                if not employee_status:
                    employee_available = False
                if row["department_id"] != department_id:
                    checks.append(
                        {
                            "check": "department_membership",
                            "status": "unavailable",
                            "detail": "EMPLOYEE_DEPARTMENT_MISMATCH",
                        }
                    )
                    employee_available = False
                else:
                    checks.append(
                        {
                            "check": "department_membership",
                            "status": "available",
                            "detail": department_id,
                        }
                    )

                profile_available = (
                    row["profile_version_status"] == "published"
                    and row["profile_status"] == "active"
                )
                checks.append(
                    {
                        "check": "profile_version",
                        "status": "available" if profile_available else "unavailable",
                        "detail": str(row["profile_version_status"] or "missing"),
                    }
                )
                if not profile_available:
                    employee_available = False

                profile_catalog_available = row["catalog_release_id"] == catalog_release_id
                checks.append(
                    {
                        "check": "catalog_release",
                        "status": "available" if profile_catalog_available else "unavailable",
                        "detail": str(row["catalog_release_id"] or "missing"),
                    }
                )
                if not profile_catalog_available:
                    employee_available = False

                try:
                    binding = json.loads(row["runtime_binding_json"] or "{}")
                except (TypeError, ValueError):
                    binding = {}
                if not isinstance(binding, dict):
                    binding = {}

                profile_type = str(row["profile_type"] or "")
                model_id = ""
                adapter_type = ""
                binding_available = True
                if profile_type == "agent_cli":
                    agent_value = str(
                        binding.get("agent_cli")
                        or binding.get("agent_key")
                        or binding.get("adapter_type")
                        or ""
                    ).strip()
                    if not agent_value:
                        binding_available = False
                    model_id = agent_value
                    adapter_type = {
                        "codex_cli": "codex_cli",
                        "claude_code": "claude_code",
                        "opencode": "opencode",
                    }.get(agent_value, "codex_cli")
                elif profile_type == "api_model":
                    model_id = str(binding.get("api_model") or binding.get("model") or "").strip()
                    required_fields = (
                        model_id,
                        str(binding.get("credential_ref") or "").strip(),
                        str(binding.get("provider_release_id") or "").strip(),
                        str(binding.get("model_binding_id") or "").strip(),
                        str(binding.get("provider_protocol") or "").strip(),
                    )
                    binding_available = all(required_fields)
                    adapter_type = "api_model"
                else:
                    binding_available = False

                checks.append(
                    {
                        "check": "runtime_binding",
                        "status": "available" if binding_available else "unavailable",
                        "detail": profile_type or "missing",
                    }
                )
                if not binding_available:
                    employee_available = False

                workspace_available = bool(workspace_grant_id)
                checks.append(
                    {
                        "check": "workspace_grant",
                        "status": "available" if workspace_available else "unavailable",
                        "detail": workspace_grant_id or "missing",
                    }
                )
                if not workspace_available:
                    employee_available = False

                resources[employee_id] = {
                    "department_id": department_id,
                    "profile_version_id": row["base_profile_version_id"],
                    "binding": binding,
                    "adapter_type": adapter_type,
                    "model_id": model_id,
                    "available": employee_available,
                    "checks": checks,
                }
                all_available = all_available and employee_available

    return resources, all_available


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
    if not isinstance(dept_tasks_def, list) or not dept_tasks_def:
        raise ValueError("PLAN_INVALID")

    # Review specs are keyed on (company_task, artifact_type) and lazily
    # dispatched when an artifact of that type is published.  Two deliverables
    # sharing an artifact_type would collide on the UNIQUE constraint and the
    # second spec would be silently dropped (no reviews, or the wrong ones), so
    # reject the plan loudly instead of letting confirm degrade quietly.
    seen_artifact_types: set[str] = set()
    for _dt in dept_tasks_def:
        for _deliv in _dt.get("deliverables", []):
            _atype = str(_deliv.get("artifact_type", "artifact"))
            if _atype in seen_artifact_types:
                raise ValueError("DUPLICATE_DELIVERABLE_ARTIFACT_TYPE")
            seen_artifact_types.add(_atype)

    cursor = await db.execute(
        "SELECT id, current_revision_id FROM companies WHERE id=?",
        (command.company_id,),
    )
    company_row = await cursor.fetchone()
    if company_row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    company_revision_id: str = company_row["current_revision_id"] or ""
    if not company_revision_id:
        raise ValueError("COMPANY_REVISION_NOT_FOUND")
    workspace_row = await (
        await db.execute(
            """SELECT tw.id, tw.repository_root, tw.workspace_grant_id
               FROM task_workspaces tw
               JOIN workspace_grants wg
                 ON wg.id=tw.workspace_grant_id AND wg.company_id=tw.company_id
                AND wg.status='active'
               WHERE tw.company_task_id=? AND tw.company_id=? AND tw.status='active'
               LIMIT 1""",
            (command.company_task_id, command.company_id),
        )
    ).fetchone()
    if workspace_row is None:
        raise ValueError("TASK_WORKSPACE_NOT_READY")
    task_workspace_id = workspace_row["id"]
    workspace_grant_id = workspace_row["workspace_grant_id"]
    if command.workspace_grant_ids and workspace_grant_id not in set(command.workspace_grant_ids):
        raise ValueError("WORKSPACE_GRANT_MISMATCH")

    cursor = await db.execute(
        "SELECT company_conversation_id FROM company_tasks WHERE id=? AND company_id=?",
        (command.company_task_id, command.company_id),
    )
    conv_row = await cursor.fetchone()
    conversation_id = conv_row["company_conversation_id"] if conv_row else _id()

    catalog_release_id = await _active_catalog_release(db)
    if catalog_release_id is None:
        # A plan cannot be confirmed until the catalog sync transaction has
        # published a verified release.
        return {
            "status": "waiting_resource",
            "company_task_version": command.expected_version,
        }

    avail_checks = await _run_availability_checks(db, command.company_id)
    if avail_checks["overall"] == "unavailable":
        return {
            "status": "waiting_resource",
            "company_task_version": command.expected_version,
        }

    employee_resources, employees_available = await _prepare_employee_resources(
        db,
        company_id=command.company_id,
        department_tasks=dept_tasks_def,
        catalog_release_id=catalog_release_id,
        workspace_grant_id=workspace_grant_id,
    )
    if not employees_available:
        return {
            "status": "waiting_resource",
            "company_task_version": command.expected_version,
        }

    created_dept_tasks: list[str] = []
    created_emp_tasks: list[str] = []
    local_ref_to_dept_task: dict[str, str] = {}
    availability_expires_at = (
        datetime.now(UTC) + timedelta(minutes=5)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")

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
            contributor_ids = [str(v) for v in deliv.get("contributor_employee_ids", [])]
            strategy = str(deliv.get("review_strategy", "independent_drafts") or "independent_drafts")
            if strategy not in {
                "independent_drafts",
                "section_partition",
                "primary_with_peer_review",
                "sequential_refinement",
            }:
                strategy = "independent_drafts"
            is_sequential = strategy == "sequential_refinement"

            # Freeze the per-deliverable review spec so the lazy dispatcher
            # can seed round-1 assignments the moment the artifact is
            # published.  Reviewer non-contributor membership is re-checked at
            # dispatch time against this contributor set.
            await db.execute(
                "INSERT OR IGNORE INTO deliverable_review_specs"
                " (id, company_id, company_task_id, department_task_id,"
                " artifact_type, review_strategy,"
                " contributor_employee_ids_json, reviewer_employee_ids_json,"
                " review_rounds, confidence_threshold, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    _id(),
                    command.company_id,
                    command.company_task_id,
                    dept_task_id,
                    str(deliv.get("artifact_type", "artifact")),
                    strategy,
                    json.dumps(contributor_ids),
                    json.dumps([str(v) for v in deliv.get("reviewer_employee_ids", [])]),
                    int(deliv.get("review_rounds", 2) or 2),
                    0.7,
                    now,
                ),
            )

            if strategy == "primary_with_peer_review":
                # Only the primary contributor produces; peers act as
                # reviewers and are scheduled lazily on artifact publication.
                contributor_ids = contributor_ids[:1]

            previous_task_id: str | None = None
            for emp_id in contributor_ids:
                emp_task_id = _id()
                deferred = is_sequential and previous_task_id is not None
                if deferred:
                    task_status = "waiting_resource"
                    resume_state: str | None = "assigned"
                else:
                    task_status = "assigned" if initial_status == "ready" else "waiting_resource"
                    # waiting_resource requires a resume target per the table
                    # CHECK; waiting_dependency segments resume to assigned.
                    resume_state = "assigned" if task_status == "waiting_resource" else None
                await db.execute(
                    "INSERT INTO employee_tasks"
                    " (id, company_id, department_task_id, employee_id,"
                    " task_kind, objective, acceptance_criteria_json,"
                    " status, resume_state, created_at, updated_at, version)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        emp_task_id,
                        command.company_id,
                        dept_task_id,
                        emp_id,
                        "standard",
                        objective,
                        json.dumps(dt_def.get("acceptance_criteria", [])),
                        task_status,
                        resume_state,
                        now,
                        now,
                        1,
                    ),
                )
                created_emp_tasks.append(emp_task_id)

                if is_sequential and previous_task_id is not None:
                    await db.execute(
                        "INSERT INTO employee_task_dependencies"
                        " (employee_task_id, depends_on_task_id, company_id, created_at)"
                        " VALUES (?,?,?,?)",
                        (emp_task_id, previous_task_id, command.company_id, now),
                    )

                resource = employee_resources[emp_id]
                profile_version_id = resource["profile_version_id"]
                binding = resource["binding"]
                adapter_type = resource["adapter_type"]
                model_id = resource["model_id"]

                cursor = await db.execute(
                    "SELECT current_revision_id FROM departments WHERE id=? AND company_id=?",
                    (department_id, command.company_id),
                )
                dept_rev_row = await cursor.fetchone()
                dept_revision_id: str = dept_rev_row["current_revision_id"] if dept_rev_row else ""
                if not dept_revision_id:
                    raise ValueError("DEPARTMENT_REVISION_NOT_FOUND")

                if deferred:
                    # Freeze the exact profile/binding/revision resolved by
                    # this confirm transaction for later lazy dispatch.
                    await db.execute(
                        "INSERT INTO employee_task_dispatch_specs"
                        " (employee_task_id, company_id, company_task_id,"
                        " department_task_id, employee_id, profile_version_id,"
                        " catalog_release_id, runtime_binding_json,"
                        " adapter_type, model_id, task_workspace_id,"
                        " company_revision_id, department_revision_id,"
                        " conversation_id, workspace_repository_root,"
                        " workspace_grant_id, created_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            emp_task_id,
                            command.company_id,
                            command.company_task_id,
                            dept_task_id,
                            emp_id,
                            profile_version_id,
                            catalog_release_id,
                            json.dumps(binding),
                            adapter_type,
                            model_id,
                            task_workspace_id,
                            company_revision_id,
                            dept_revision_id,
                            conversation_id,
                            workspace_row["repository_root"],
                            workspace_grant_id,
                            now,
                        ),
                    )
                else:
                    await build_run(
                        db,
                        RunSpec(
                            company_id=command.company_id,
                            company_task_id=command.company_task_id,
                            department_task_id=dept_task_id,
                            department_id=department_id,
                            employee_task_id=emp_task_id,
                            employee_id=emp_id,
                            conversation_id=conversation_id,
                            task_workspace_id=task_workspace_id,
                            workspace_repository_root=workspace_row["repository_root"],
                            workspace_grant_id=workspace_grant_id,
                            company_revision_id=company_revision_id,
                            department_revision_id=dept_revision_id,
                            profile_version_id=profile_version_id,
                            catalog_release_id=catalog_release_id,
                            runtime_binding_json=json.dumps(binding),
                            adapter_type=adapter_type,
                            model_id=model_id,
                            objective=objective,
                            availability_expires_at=availability_expires_at,
                            run_purpose="task_execution",
                            priority=0,
                            checks=resource["checks"],
                            now=now,
                        ),
                    )
                previous_task_id = emp_task_id

    plan_artifact_id = command.plan_artifact_id
    plan_artifact_sha = hashlib.sha256(plan_row["canonical_json"].encode()).hexdigest()
    plan_meta = json.dumps(
        {
            "plan_version_id": plan_row["id"],
            "version_number": plan_row["version_number"],
            "goal": goal,
            "company_task_id": command.company_task_id,
        },
        sort_keys=True,
    )
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

    # The status machine does not contain an implicit composite edge.  Apply
    # each allowed edge and append its event/outbox row, so recovery and
    # projections observe the same sequence as the persisted aggregate.
    status_path = (
        ("awaiting_user_confirmation", "approved"),
        ("approved", "dispatching"),
        ("dispatching", "checking_resources"),
        ("checking_resources", "executing"),
    )
    current_version = int(task_row["version"])
    plan_update = await db.execute(
        "UPDATE company_plan_versions SET status='approved', confirmed_at=?"
        " WHERE id=? AND company_id=? AND status='awaiting_user_confirmation'",
        (now, plan_row["id"], command.company_id),
    )
    if plan_update.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    for from_state, to_state in status_path:
        next_version = current_version + 1
        cursor = await db.execute(
            "UPDATE company_tasks SET status=?, version=?, updated_at=?"
            " WHERE id=? AND company_id=? AND status=? AND version=?",
            (
                to_state,
                next_version,
                now,
                command.company_task_id,
                command.company_id,
                from_state,
                current_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        payload = {
            "company_id": command.company_id,
            "aggregate_id": command.company_task_id,
            "version": next_version,
            "from_state": from_state,
            "to_state": to_state,
        }
        company_event_id = _id()
        await _insert_domain_event(
            db,
            company_event_id,
            command.company_id,
            "company_task",
            command.company_task_id,
            next_version,
            "company_task.status_changed",
            payload,
            trace_id,
            now,
        )
        await _insert_outbox(
            db,
            _id(),
            company_event_id,
            "company_task.status_changed",
            payload,
            now,
        )
        current_version = next_version

    return {
        "status": "confirmed",
        "company_task_version": current_version,
    }
