"""Review assignment and reporting service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def assign_reviewer(
    db: Any,
    company_id: str,
    *,
    artifact_id: str,
    reviewer_employee_id: str,
    review_round: int,
    reviewed_sha256: str,
) -> dict[str, object]:
    """Assign a reviewer to an artifact (non-contributor enforcement)."""
    assignment_id = _id()
    now = _now()

    contributor = await _one(
        await db.execute(
            """SELECT 1 FROM artifact_contributors
               WHERE artifact_id=? AND company_id=? AND employee_id=?""",
            (artifact_id, company_id, reviewer_employee_id),
        )
    )
    if contributor is not None:
        raise ValueError("REVIEWER_CANNOT_BE_CONTRIBUTOR")

    artifact = await _one(
        await db.execute(
            "SELECT object_sha256 FROM artifacts WHERE id=? AND company_id=? AND is_current=1",
            (artifact_id, company_id),
        )
    )
    if artifact is None:
        raise ValueError("ARTIFACT_NOT_FOUND")
    if artifact["object_sha256"] != reviewed_sha256:
        raise ValueError("ARTIFACT_SHA_MISMATCH")
    reviewer = await _one(
        await db.execute(
            "SELECT 1 FROM employees WHERE id=? AND company_id=? AND status='active'",
            (reviewer_employee_id, company_id),
        )
    )
    if reviewer is None:
        raise ValueError("REVIEWER_NOT_AVAILABLE")

    existing = await _one(
        await db.execute(
            """SELECT id FROM review_assignments
               WHERE artifact_id=? AND company_id=?
               AND reviewer_employee_id=? AND review_round=?""",
            (artifact_id, company_id, reviewer_employee_id, review_round),
        )
    )
    if existing is not None:
        raise ValueError("REVIEWER_ALREADY_ASSIGNED")

    await db.execute(
        """INSERT INTO review_assignments
           (id, company_id, artifact_id, reviewer_employee_id,
            review_round, reviewed_sha256, status, assigned_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            assignment_id,
            company_id,
            artifact_id,
            reviewer_employee_id,
            review_round,
            reviewed_sha256,
            "assigned",
            now,
        ),
    )

    payload = json.dumps(
        {
            "company_id": company_id,
            "aggregate_id": assignment_id,
            "version": 1,
            "assignment_id": assignment_id,
            "reviewer_employee_id": reviewer_employee_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    event_id = _id()
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?, ?, 'review_assignment', ?, 1, 'review.assigned', ?, ?, ?)""",
        (event_id, company_id, assignment_id, payload, _id(), now),
    )
    await db.execute(
        """INSERT INTO outbox_events
           (id, domain_event_id, topic, payload_json, status, attempts,
            next_attempt_at, created_at)
           VALUES (?, ?, 'review.assigned', ?, 'pending', 0, ?, ?)""",
        (_id(), event_id, payload, now, now),
    )

    return {
        "id": assignment_id,
        "artifact_id": artifact_id,
        "reviewer_employee_id": reviewer_employee_id,
        "review_round": review_round,
        "status": "assigned",
        "version": 1,
    }


async def assign_existing_reviewer(
    db: Any,
    company_id: str,
    *,
    assignment_id: str,
    reviewer_employee_id: str,
) -> dict[str, object]:
    """Bind a reviewer to an existing assignment with optimistic locking."""
    assignment = await _one(
        await db.execute(
            """SELECT id, artifact_id, reviewed_sha256, reviewer_employee_id, status, version
               FROM review_assignments WHERE id=? AND company_id=?""",
            (assignment_id, company_id),
        )
    )
    if assignment is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    if assignment["status"] not in ("assigned", "in_review"):
        raise ValueError("STATE_TRANSITION_INVALID")
    reviewer = await _one(
        await db.execute(
            "SELECT 1 FROM employees WHERE id=? AND company_id=? AND status='active'",
            (reviewer_employee_id, company_id),
        )
    )
    if reviewer is None:
        raise ValueError("REVIEWER_NOT_AVAILABLE")
    contributor = await _one(
        await db.execute(
            """SELECT 1 FROM artifact_contributors
               WHERE artifact_id=? AND company_id=? AND employee_id=?""",
            (assignment["artifact_id"], company_id, reviewer_employee_id),
        )
    )
    if contributor is not None:
        raise ValueError("REVIEWER_CANNOT_BE_CONTRIBUTOR")
    next_version = int(assignment["version"]) + 1
    cursor = await db.execute(
        """UPDATE review_assignments
           SET reviewer_employee_id=?, version=?
           WHERE id=? AND company_id=? AND version=?""",
        (reviewer_employee_id, next_version, assignment_id, company_id, assignment["version"]),
    )
    if cursor.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    now = _now()
    payload = json.dumps(
        {
            "company_id": company_id,
            "aggregate_id": assignment_id,
            "version": next_version,
            "assignment_id": assignment_id,
            "reviewer_employee_id": reviewer_employee_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    event_id = _id()
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?, ?, 'review_assignment', ?, ?, 'review.assigned', ?, ?, ?)""",
        (event_id, company_id, assignment_id, next_version, payload, _id(), now),
    )
    await db.execute(
        """INSERT INTO outbox_events
           (id, domain_event_id, topic, payload_json, status, attempts,
            next_attempt_at, created_at)
           VALUES (?, ?, 'review.assigned', ?, 'pending', 0, ?, ?)""",
        (_id(), event_id, payload, now, now),
    )
    return {"success": True, "version": next_version}


async def start_review(
    db: Any,
    company_id: str,
    *,
    assignment_id: str,
) -> dict[str, object]:
    """Transition an assignment from 'assigned' to 'in_review'."""
    cursor = await db.execute(
        """UPDATE review_assignments
           SET status='in_review'
           WHERE id=? AND company_id=? AND status='assigned'""",
        (assignment_id, company_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("STATE_TRANSITION_INVALID")

    return {
        "id": assignment_id,
        "status": "in_review",
    }


async def submit_review_report(
    db: Any,
    company_id: str,
    *,
    assignment_id: str,
    artifact_id: str,
    artifact_sha256: str,
    report_artifact_id: str,
    reviewer_run_id: str,
    verdict: str,
    summary: str,
    issues: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Submit a review report for an assignment.

    Validates:
    - The artifact SHA matches the database record.
    - The reviewer is not a contributor of the artifact.
    - New artifact version auto-invalidates old reviews (marks them stale).
    """
    report_id = _id()
    now = _now()

    assignment = await _one(
        await db.execute(
            """SELECT * FROM review_assignments
               WHERE id=? AND company_id=?""",
            (assignment_id, company_id),
        )
    )
    if assignment is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    if assignment["status"] not in ("assigned", "in_review"):
        raise ValueError("STATE_TRANSITION_INVALID")
    if reviewer_run_id is None:
        raise ValueError("REVIEWER_RUN_ID_REQUIRED")

    if assignment["artifact_id"] != artifact_id or assignment["reviewed_sha256"] != artifact_sha256:
        raise ValueError("REVIEW_ARTIFACT_MISMATCH")

    artifact = await _one(
        await db.execute(
            """SELECT object_sha256, is_current FROM artifacts WHERE id=? AND company_id=?""",
            (artifact_id, company_id),
        )
    )
    if artifact is None:
        raise ValueError("ARTIFACT_NOT_FOUND")
    if dict(artifact)["object_sha256"] != artifact_sha256 or int(artifact["is_current"]) != 1:
        raise ValueError("ARTIFACT_SHA_MISMATCH")

    report_artifact = await _one(
        await db.execute(
            """SELECT artifact_type, created_by_type, created_by_run_id
               FROM artifacts WHERE id=? AND company_id=?""",
            (report_artifact_id, company_id),
        )
    )
    if (
        report_artifact is None
        or report_artifact["artifact_type"] != "review_report"
        or report_artifact["created_by_type"] != "agent"
        or report_artifact["created_by_run_id"] != reviewer_run_id
    ):
        raise ValueError("REVIEW_REPORT_ARTIFACT_MISMATCH")

    run = await _one(
        await db.execute(
            """SELECT employee_id, run_purpose, status FROM agent_runs
               WHERE id=? AND company_id=?""",
            (reviewer_run_id, company_id),
        )
    )
    if (
        run is None
        or run["employee_id"] != assignment["reviewer_employee_id"]
        or run["run_purpose"] != "review"
        or run["status"] != "succeeded"
    ):
        raise ValueError("REVIEW_RUN_BINDING_MISMATCH")

    contributor = await _one(
        await db.execute(
            """SELECT 1 FROM artifact_contributors
               WHERE artifact_id=? AND company_id=?
               AND employee_id IN (
                   SELECT reviewer_employee_id FROM review_assignments WHERE id=?
               )
               LIMIT 1""",
            (artifact_id, company_id, assignment_id),
        )
    )
    if contributor is not None:
        raise ValueError("REVIEWER_CANNOT_BE_CONTRIBUTOR")

    superseding = await _one(
        await db.execute(
            """SELECT id FROM artifacts
               WHERE supersedes_artifact_id=? AND company_id=?
               LIMIT 1""",
            (artifact_id, company_id),
        )
    )

    if superseding is not None:
        new_status = "stale"
    else:
        new_status = "submitted"

    await db.execute(
        """INSERT INTO review_reports
            (id, company_id, assignment_id, reviewer_run_id,
            reviewed_artifact_id, reviewed_sha256, verdict,
            report_artifact_id, version, created_at)
           VALUES (?,?,?,?,?,?,?,?,1,?)""",
        (
            report_id,
            company_id,
            assignment_id,
            reviewer_run_id,
            artifact_id,
            artifact_sha256,
            verdict,
            report_artifact_id,
            now,
        ),
    )

    if issues:
        for iss in issues:
            await db.execute(
                """INSERT INTO review_issues
                   (id, company_id, review_report_id, severity, category,
                    description, expected, actual, suggested_fix,
                    evidence_refs_json, status, assignee_employee_id,
                    verifier_employee_id, created_at, updated_at, version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _id(),
                    company_id,
                    report_id,
                    iss.get("severity", "medium"),
                    iss.get("category", "general"),
                    iss.get("description", ""),
                    iss.get("expected", ""),
                    iss.get("actual", ""),
                    iss.get("suggested_fix", ""),
                    json.dumps([str(ref) for ref in iss.get("evidence_refs", [])], separators=(",", ":")),
                    "open",
                    None,
                    None,
                    now,
                    now,
                    1,
                ),
            )

    if superseding is not None:
        await db.execute(
            """UPDATE review_assignments
               SET status='stale'
               WHERE artifact_id=? AND company_id=?
               AND status IN ('assigned','in_review','submitted')""",
            (artifact_id, company_id),
        )

    cursor = await db.execute(
        """UPDATE review_assignments
           SET status=?, submitted_at=?, version=version+1
           WHERE id=? AND company_id=? AND version=?""",
        (new_status, now, assignment_id, company_id, assignment["version"]),
    )
    if cursor.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

    return {
        "id": report_id,
        "assignment_id": assignment_id,
        "artifact_id": artifact_id,
        "verdict": verdict,
        "status": new_status,
    }


async def create_review_issue(
    db: Any,
    company_id: str,
    *,
    report_id: str,
    severity: str,
    category: str,
    description: str,
    expected: str,
    actual: str,
    suggested_fix: str,
    file_path: str | None = None,
    line_number: int | None = None,
) -> dict[str, object]:
    """Create an issue from a review report."""
    issue_id = _id()
    now = _now()
    evidence_refs = json.dumps(
        [{"file_path": file_path, "line_number": line_number}] if file_path is not None else [],
        separators=(",", ":"),
    )

    await db.execute(
        """INSERT INTO review_issues
           (id, company_id, review_report_id, severity, category,
            description, expected, actual, suggested_fix,
            evidence_refs_json, status, assignee_employee_id,
            verifier_employee_id, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            issue_id,
            company_id,
            report_id,
            severity,
            category,
            description,
            expected,
            actual,
            suggested_fix,
            evidence_refs,
            "open",
            None,
            None,
            now,
            now,
            1,
        ),
    )

    return {
        "id": issue_id,
        "report_id": report_id,
        "severity": severity,
        "status": "open",
    }


async def start_fixing_review_issue(
    db: Any,
    company_id: str,
    *,
    issue_id: str,
) -> dict[str, object]:
    """Transition a review issue from open to fixing."""
    now = _now()

    cursor = await db.execute(
        """UPDATE review_issues
           SET status='fixing', updated_at=?, version=version+1
           WHERE id=? AND company_id=? AND status='open'""",
        (now, issue_id, company_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("STATE_TRANSITION_INVALID")

    return {
        "id": issue_id,
        "status": "fixing",
    }


async def list_review_issues(
    db: Any,
    company_id: str,
    *,
    report_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    """List review issues with optional filters."""
    conditions = ["company_id=?"]
    params: list[Any] = [company_id]

    if report_id is not None:
        conditions.append("review_report_id=?")
        params.append(report_id)
    if status is not None:
        conditions.append("status=?")
        params.append(status)

    where = " AND ".join(conditions)
    params.append(limit)

    cursor = await db.execute(
        f"""SELECT * FROM review_issues
            WHERE {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?""",
        tuple(params),
    )
    return [dict(row) for row in await cursor.fetchall()]
