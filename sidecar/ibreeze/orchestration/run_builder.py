"""Reusable run construction for deterministic dispatch.

The confirm transaction (``orchestration/confirm_plan.py``) and the lazy
``employee_task.graph_advance`` dispatcher both need to build the identical
set of rows: availability snapshot, execution snapshot, agent run and runtime
queue entry.  This module centralises that build so both callers are
guaranteed to produce byte-identical runtime bindings.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True, slots=True)
class RunSpec:
    company_id: str
    company_task_id: str
    department_task_id: str
    department_id: str
    employee_task_id: str
    employee_id: str
    conversation_id: str
    task_workspace_id: str
    workspace_repository_root: str
    workspace_grant_id: str
    company_revision_id: str
    department_revision_id: str
    profile_version_id: str
    catalog_release_id: str
    runtime_binding_json: str
    adapter_type: str
    model_id: str
    objective: str
    availability_expires_at: str
    run_purpose: str = "task_execution"
    priority: int = 0
    checks: list[dict[str, str]] = field(default_factory=list)
    now: str | None = None
    routing_policy_json: str = "{}"
    routing_policy_sha256: str | None = None
    routing_classifier_version: str | None = None
    candidate_bindings_json: str | None = None
    candidate_bindings_sha256: str | None = None
    profile_type: str = "agent_cli"
    required_capability_tags: tuple[str, ...] = ()


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def build_run(
    db: Any,
    spec: RunSpec,
) -> dict[str, str]:
    """Insert availability/execution snapshots, agent run and queue row.

    Returns ``{"run_id":..., "job_id":..., "avail_snap_id":...,
    "exec_snap_id":..., "spec_sha256":...}`` for event wiring.
    """
    now = spec.now or _now_iso()
    run_id = _id()
    job_id = _id()
    avail_snap_id = _id()
    exec_snap_id = _id()

    try:
        binding = json.loads(spec.runtime_binding_json or "{}")
    except (TypeError, ValueError):
        binding = {}
    if not isinstance(binding, dict):
        binding = {}

    run_spec = {
        "prompt": spec.objective,
        "model_id": spec.model_id,
        "workspace": spec.workspace_repository_root,
        "workspace_grant_id": spec.workspace_grant_id,
        "agent_key": binding.get("agent_cli"),
        "credential_ref": binding.get("credential_ref", ""),
        "provider_release_id": binding.get("provider_release_id", ""),
        "model_binding_id": binding.get("model_binding_id", ""),
        "provider_protocol": binding.get("provider_protocol", ""),
        "run_purpose": spec.run_purpose,
        "adapter_type": spec.adapter_type,
        "required_capability_tags": list(spec.required_capability_tags),
    }
    if spec.adapter_type == "api_model":
        # API-model runs carry the resolved model id; CLI adapters select their
        # own default model when the key is absent (see runtime/adapters/*.py).
        run_spec["model"] = spec.model_id
    candidate_json: str | None
    candidate_hash: str | None
    if spec.profile_type == "api_model" and spec.candidate_bindings_json is None:
        from ibreeze.routing.candidates import resolve_candidate_bindings

        (
            candidate_json,
            candidate_hash,
            _routing_mode,
        ) = await resolve_candidate_bindings(
            db,
            company_id=spec.company_id,
            employee_id=spec.employee_id,
            catalog_release_id=spec.catalog_release_id,
            profile_type=spec.profile_type,
            runtime_binding=binding,
            routing_policy_json=spec.routing_policy_json,
        )
    else:
        candidate_json = spec.candidate_bindings_json
        candidate_hash = spec.candidate_bindings_sha256
    spec_json = json.dumps(run_spec, sort_keys=True, separators=(",", ":"))
    spec_sha = hashlib.sha256(spec_json.encode()).hexdigest()

    availability_checks = {
        "checks": spec.checks,
        "overall": "available",
    }
    await db.execute(
        "INSERT INTO employee_availability_snapshots"
        " (id, company_id, company_task_id, department_task_id,"
        " work_item_type, work_item_id, employee_id,"
        " base_profile_version_id, prospective_execution_sha256,"
        " catalog_release_id, checks_json, overall_status,"
        " checked_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            avail_snap_id,
            spec.company_id,
            spec.company_task_id,
            spec.department_task_id,
            spec.run_purpose,
            spec.employee_task_id,
            spec.employee_id,
            spec.profile_version_id,
            spec_sha,
            spec.catalog_release_id,
            json.dumps(availability_checks),
            "available",
            now,
            spec.availability_expires_at,
        ),
    )

    await db.execute(
        "INSERT INTO execution_snapshots"
        " (id, company_id, company_task_id, department_id,"
        " department_task_id, employee_task_id, employee_id, task_workspace_id,"
        " snapshot_purpose, work_item_id, company_revision_id,"
        " department_revision_id, base_profile_version_id,"
        " catalog_release_id, runtime_binding_json,"
        " skill_lock_json, tool_policy_json,"
        " workspace_policy_json, verification_commands_json,"
        " content_sha256, routing_policy_json, routing_policy_sha256, routing_classifier_version,"
        " candidate_bindings_json, candidate_bindings_sha256, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            exec_snap_id,
            spec.company_id,
            spec.company_task_id,
            spec.department_id,
            spec.department_task_id,
            spec.employee_task_id,
            spec.employee_id,
            spec.task_workspace_id,
            spec.run_purpose,
            spec.employee_task_id,
            spec.company_revision_id,
            spec.department_revision_id,
            spec.profile_version_id,
            spec.catalog_release_id,
            json.dumps(binding),
            "{}",
            "{}",
            "{}",
            "[]",
            spec_sha,
            spec.routing_policy_json,
            spec.routing_policy_sha256,
            spec.routing_classifier_version or ("rules-v1" if spec.profile_type == "api_model" else None),
            candidate_json,
            candidate_hash,
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
            spec.company_id,
            spec.company_task_id,
            spec.department_task_id,
            spec.employee_task_id,
            spec.employee_task_id,
            spec.employee_id,
            spec.conversation_id,
            avail_snap_id,
            exec_snap_id,
            spec.run_purpose,
            spec.adapter_type,
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
        " VALUES (?,?, 'employee_task', ?, ?, ?, ?, 'ready', ?)",
        (_id(), spec.company_id, spec.employee_task_id, job_id, run_id, spec.priority, now),
    )

    return {
        "run_id": run_id,
        "job_id": job_id,
        "avail_snap_id": avail_snap_id,
        "exec_snap_id": exec_snap_id,
        "spec_sha256": spec_sha,
    }
