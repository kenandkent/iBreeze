"""Collaboration-strategy graph continuation: lazy dispatch and review seeding.

The confirm transaction (``orchestration/confirm_plan.py``) materialises the
execution graph from each deliverable's ``review_strategy``.  Two of the four
strategies need runtime continuation after that single transaction:

* ``sequential_refinement`` — only the first segment is dispatched at confirm
  time.  Later segments are inserted in ``waiting_resource`` with a frozen
  ``employee_task_dispatch_specs`` row and are dispatched exactly once by
  :func:`advance_employee_task_graph` once every upstream segment is accepted.
* every strategy — reviewers never get an employee task.  Round-1 review
  assignments are created lazily by :func:`maybe_dispatch_deliverable_reviews`
  the moment a contributor publishes the current artifact, using the frozen
  ``deliverable_review_specs`` row written at confirm time.

Both functions run inside the caller's already-open transaction (the confirm
transaction or the ``artifact.create`` UnitOfWork), so they are atomic with
the state they observe.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ibreeze.orchestration.run_builder import RunSpec, build_run

logger = logging.getLogger(__name__)


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def maybe_dispatch_deliverable_reviews(
    db: Any,
    *,
    company_id: str,
    company_task_id: str,
    artifact_id: str,
    artifact_type: str,
    is_current: bool,
) -> list[dict[str, Any]]:
    """Create round-1 review assignments the moment an artifact is published.

    Only a current artifact of a type covered by a frozen
    ``deliverable_review_specs`` row schedules reviewers.  Each reviewer that
    is still active and is not a contributor gets one ``assigned`` assignment
    guarded by ``UNIQUE(artifact_id, reviewer_employee_id, review_round)``, so
    replays and deduplicated publishes are no-ops.  ``review.assigned`` is a
    projection-only outbox topic; no completion gate is advanced here.

    Returns the assignments actually created.
    """
    if not is_current:
        return []
    cursor = await db.execute(
        """SELECT id, review_strategy, reviewer_employee_ids_json,
                  contributor_employee_ids_json
           FROM deliverable_review_specs
           WHERE company_id=? AND company_task_id=? AND artifact_type=?""",
        (company_id, company_task_id, artifact_type),
    )
    spec = await cursor.fetchone()
    if spec is None:
        return []
    try:
        reviewers = json.loads(spec["reviewer_employee_ids_json"] or "[]")
        contributors = set(json.loads(spec["contributor_employee_ids_json"] or "[]"))
    except (TypeError, ValueError):
        return []
    if not isinstance(reviewers, list) or not reviewers:
        return []

    cursor = await db.execute(
        "SELECT object_sha256 FROM artifacts WHERE id=? AND company_id=? AND is_current=1",
        (artifact_id, company_id),
    )
    artifact = await cursor.fetchone()
    if artifact is None:
        return []

    now = _now()
    reviewed_sha256 = artifact["object_sha256"]
    created: list[dict[str, Any]] = []
    for reviewer_value in reviewers:
        reviewer_id = str(reviewer_value)
        if reviewer_id in contributors:
            continue
        reviewer_row = await (
            await db.execute(
                "SELECT 1 FROM employees WHERE id=? AND company_id=? AND status='active'",
                (reviewer_id, company_id),
            )
        ).fetchone()
        if reviewer_row is None:
            continue
        contributor_row = await (
            await db.execute(
                """SELECT 1 FROM artifact_contributors
                   WHERE artifact_id=? AND company_id=? AND employee_id=?""",
                (artifact_id, company_id, reviewer_id),
            )
        ).fetchone()
        if contributor_row is not None:
            continue
        assignment_id = _id()
        cursor = await db.execute(
            """INSERT OR IGNORE INTO review_assignments
               (id, company_id, artifact_id, reviewer_employee_id,
                review_round, reviewed_sha256, status, assigned_at)
               VALUES (?,?,?,?,1,?,'assigned',?)""",
            (assignment_id, company_id, artifact_id, reviewer_id, reviewed_sha256, now),
        )
        if cursor.rowcount != 1:
            continue
        payload = {
            "company_id": company_id,
            "aggregate_id": assignment_id,
            "version": 1,
            "assignment_id": assignment_id,
            "reviewer_employee_id": reviewer_id,
        }
        event_id = _id()
        await db.execute(
            """INSERT INTO domain_events
               (event_id, company_id, aggregate_type, aggregate_id,
                aggregate_version, event_type, payload_json, trace_id, occurred_at)
               VALUES (?, ?, 'review_assignment', ?, 1, 'review.assigned', ?, ?, ?)""",
            (event_id, company_id, assignment_id, json.dumps(payload, sort_keys=True), _id(), now),
        )
        await db.execute(
            """INSERT INTO outbox_events
               (id, domain_event_id, topic, payload_json, status, attempts,
                next_attempt_at, created_at)
               VALUES (?, ?, 'review.assigned', ?, 'pending', 0, ?, ?)""",
            (_id(), event_id, json.dumps(payload, sort_keys=True), now, now),
        )
        created.append(
            {
                "assignment_id": assignment_id,
                "reviewer_employee_id": reviewer_id,
                "review_round": 1,
            }
        )
    return created


async def advance_employee_task_graph(
    db: Any,
    *,
    company_id: str,
    accepted_task_id: str,
) -> dict[str, Any]:
    """Lazily dispatch sequential-refinement segments after an upstream accept.

    Runs inside the Outbox transaction that delivered ``accepted_task_id``'s
    ``employee_task.graph_advance`` event.  For every dependent employee task
    still in ``waiting_resource`` whose *all* upstream dependencies are
    ``accepted``, it transitions the task to ``assigned``, clears
    ``resume_state`` and rebuilds the run from the frozen dispatch spec — the
    exact profile/binding/revision resolved at confirm time, with no second
    parse.  The optimistic ``WHERE status='waiting_resource'`` guard makes the
    dispatch exactly-once across replays.

    A dependent whose frozen binding is no longer live is transitioned to
    ``failed`` (see :func:`_lazy_availability_checks`) rather than left stuck
    in ``waiting_resource``; those ids are returned under the ``failed`` key.
    """
    cursor = await db.execute(
        """SELECT et2.id AS task_id, et2.department_task_id
           FROM employee_task_dependencies dep
           JOIN employee_tasks et2 ON et2.id=dep.employee_task_id AND et2.company_id=dep.company_id
           WHERE dep.depends_on_task_id=? AND dep.company_id=?
             AND et2.status='waiting_resource'""",
        (accepted_task_id, company_id),
    )
    dependents = await cursor.fetchall()

    dispatched: list[str] = []
    failed_tasks: list[str] = []
    now = _now()
    for dependent in dependents:
        task_id = dependent["task_id"]
        pending_cursor = await db.execute(
            """SELECT COUNT(*) AS pending
               FROM employee_task_dependencies dep
               WHERE dep.employee_task_id=? AND dep.company_id=?
                 AND NOT EXISTS (
                     SELECT 1 FROM employee_tasks et
                     WHERE et.id=dep.depends_on_task_id AND et.company_id=dep.company_id
                       AND et.status='accepted'
                 )""",
            (task_id, company_id),
        )
        if (await pending_cursor.fetchone())["pending"] != 0:
            continue
        spec_row = await _dispatch_spec_for(db, company_id=company_id, employee_task_id=task_id)
        if spec_row is None:
            continue
        checks, available = await _lazy_availability_checks(
            db,
            company_id=company_id,
            employee_id=spec_row["employee_id"],
            profile_version_id=spec_row["profile_version_id"],
            catalog_release_id=spec_row["catalog_release_id"],
            workspace_grant_id=spec_row["workspace_grant_id"],
        )
        if not available:
            # The frozen binding is no longer live (employee deactivated,
            # profile unpublished, catalog superseded or grant revoked).  Fail
            # the segment instead of leaving it silently stuck in
            # ``waiting_resource``: the outbox event that triggered this
            # dispatch is delivered exactly once and nothing would re-dispatch
            # a waiting segment later.  A terminal, visible ``failed`` state
            # lets an operator re-plan rather than chase a phantom.
            transition_failed = await db.execute(
                """UPDATE employee_tasks
                   SET status='failed', resume_state=NULL, updated_at=?, version=version+1
                   WHERE id=? AND company_id=? AND status='waiting_resource'""",
                (now, task_id, company_id),
            )
            if transition_failed.rowcount == 1:
                failed_tasks.append(task_id)
                logger.warning(
                    "Lazy dispatch failed for employee_task=%s (company=%s): unavailable %s",
                    task_id,
                    company_id,
                    [_c["detail"] for _c in checks if _c["status"] != "available"],
                )
            continue
        transition = await db.execute(
            """UPDATE employee_tasks
               SET status='assigned', resume_state=NULL, updated_at=?, version=version+1
               WHERE id=? AND company_id=? AND status='waiting_resource'""",
            (now, task_id, company_id),
        )
        if transition.rowcount != 1:
            continue
        await build_run(
            db,
            RunSpec(
                company_id=company_id,
                company_task_id=spec_row["company_task_id"],
                department_task_id=spec_row["department_task_id"],
                department_id=spec_row["department_id"],
                employee_task_id=task_id,
                employee_id=spec_row["employee_id"],
                conversation_id=spec_row["conversation_id"],
                task_workspace_id=spec_row["task_workspace_id"],
                workspace_repository_root=spec_row["workspace_repository_root"],
                workspace_grant_id=spec_row["workspace_grant_id"],
                company_revision_id=spec_row["company_revision_id"],
                department_revision_id=spec_row["department_revision_id"],
                profile_version_id=spec_row["profile_version_id"],
                catalog_release_id=spec_row["catalog_release_id"],
                runtime_binding_json=spec_row["runtime_binding_json"],
                adapter_type=spec_row["adapter_type"],
                model_id=spec_row["model_id"],
                objective=spec_row["objective"],
                availability_expires_at=(datetime.now(UTC) + timedelta(minutes=5))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
                run_purpose="task_execution",
                priority=0,
                checks=checks,
                now=now,
            ),
        )
        dispatched.append(task_id)
    return {"status": "advanced", "dispatched": dispatched, "failed": failed_tasks}


async def _dispatch_spec_for(
    db: Any,
    *,
    company_id: str,
    employee_task_id: str,
) -> dict[str, Any] | None:
    cursor = await db.execute(
        """SELECT ds.company_task_id, ds.department_task_id, ds.employee_id,
                  ds.profile_version_id, ds.catalog_release_id,
                  ds.runtime_binding_json, ds.adapter_type, ds.model_id,
                  ds.task_workspace_id, ds.company_revision_id,
                  ds.department_revision_id, ds.conversation_id,
                  ds.workspace_repository_root, ds.workspace_grant_id,
                  dt.department_id, dt.objective
           FROM employee_task_dispatch_specs ds
           JOIN department_tasks dt ON dt.id=ds.department_task_id AND dt.company_id=ds.company_id
           WHERE ds.employee_task_id=? AND ds.company_id=?""",
        (employee_task_id, company_id),
    )
    row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def _lazy_availability_checks(
    db: Any,
    *,
    company_id: str,
    employee_id: str,
    profile_version_id: str,
    catalog_release_id: str,
    workspace_grant_id: str,
) -> tuple[list[dict[str, str]], bool]:
    """Compact still-valid probe for a deferred sequential segment.

    The confirm transaction already performed the authoritative preflight; the
    frozen dispatch spec pins the profile, catalog release and workspace.  This
    re-probe only re-checks that those pinned references are still live before
    dispatching, so a segment is never scheduled against a retired profile or
    a revoked workspace grant.
    """
    checks: list[dict[str, str]] = []
    available = True

    row = await (
        await db.execute(
            """SELECT e.status AS employee_status,
                      v.status AS profile_version_status,
                      v.catalog_release_id, p.status AS profile_status
               FROM employees e
               LEFT JOIN employee_base_profile_versions v ON v.id=e.base_profile_version_id
               LEFT JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE e.id=? AND e.company_id=?""",
            (employee_id, company_id),
        )
    ).fetchone()
    employee_ok = row is not None and row["employee_status"] == "active"
    checks.append(
        {
            "check": "employee_status",
            "status": "available" if employee_ok else "unavailable",
            "detail": str(row["employee_status"]) if row is not None else "missing",
        }
    )
    profile_ok = (
        row is not None
        and row["profile_version_status"] == "published"
        and row["profile_status"] == "active"
    )
    checks.append(
        {
            "check": "profile_version",
            "status": "available" if profile_ok else "unavailable",
            "detail": str(row["profile_version_status"] or "missing"),
        }
    )
    catalog_ok = row is not None and row["catalog_release_id"] == catalog_release_id
    checks.append(
        {
            "check": "catalog_release",
            "status": "available" if catalog_ok else "unavailable",
            "detail": str(row["catalog_release_id"] or "missing"),
        }
    )
    workspace_ok = bool(workspace_grant_id)
    checks.append(
        {
            "check": "workspace_grant",
            "status": "available" if workspace_ok else "unavailable",
            "detail": workspace_grant_id or "missing",
        }
    )
    available = employee_ok and profile_ok and catalog_ok and workspace_ok
    return checks, available
