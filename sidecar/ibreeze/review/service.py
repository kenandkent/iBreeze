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

    await db.execute("BEGIN IMMEDIATE")
    try:
        contributor = await _one(
            await db.execute(
                """SELECT 1 FROM artifact_contributors
                   WHERE artifact_id=? AND company_id=? AND employee_id=?""",
                (artifact_id, company_id, reviewer_employee_id),
            )
        )
        if contributor is not None:
            raise ValueError("REVIEWER_CANNOT_BE_CONTRIBUTOR")

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

        await db.commit()
        return {
            "id": assignment_id,
            "artifact_id": artifact_id,
            "reviewer_employee_id": reviewer_employee_id,
            "review_round": review_round,
            "status": "assigned",
        }
    except Exception:
        await db.rollback()
        raise


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

    await db.commit()
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

    await db.execute("BEGIN IMMEDIATE")
    try:
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

        artifact = await _one(
            await db.execute(
                """SELECT object_sha256 FROM artifacts WHERE id=? AND company_id=?""",
                (artifact_id, company_id),
            )
        )
        if artifact is None:
            raise ValueError("ARTIFACT_NOT_FOUND")
        if dict(artifact)["object_sha256"] != artifact_sha256:
            raise ValueError("ARTIFACT_SHA_MISMATCH")

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
                verdict, report_artifact_id, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                report_id,
                company_id,
                assignment_id,
                reviewer_run_id,
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
                        "[]",
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

        await db.execute(
            """UPDATE review_assignments
               SET status=?, submitted_at=?
               WHERE id=? AND company_id=?""",
            (new_status, now, assignment_id, company_id),
        )

        await db.commit()
        return {
            "id": report_id,
            "assignment_id": assignment_id,
            "artifact_id": artifact_id,
            "verdict": verdict,
            "status": new_status,
        }
    except Exception:
        await db.rollback()
        raise


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
        [{"file_path": file_path, "line_number": line_number}]
        if file_path is not None
        else [],
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
    await db.commit()

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

    await db.commit()
    return {
        "id": issue_id,
        "status": "fixing",
    }


async def resolve_review_issue(
    db: Any,
    company_id: str,
    *,
    issue_id: str,
    resolution: str,
) -> dict[str, object]:
    """Resolve a review issue (fixing → resolved)."""
    now = _now()

    cursor = await db.execute(
        """UPDATE review_issues
           SET status='resolved', rejection_reason=?,
               updated_at=?, version=version+1
           WHERE id=? AND company_id=? AND status='fixing'""",
        (resolution, now, issue_id, company_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("STATE_TRANSITION_INVALID")

    await db.commit()
    return {
        "id": issue_id,
        "status": "resolved",
        "resolution": resolution,
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
