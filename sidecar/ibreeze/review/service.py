"""Review assignment and reporting service."""

from __future__ import annotations

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


async def submit_review_report(
    db: Any,
    company_id: str,
    *,
    assignment_id: str,
    report_artifact_id: str,
    verdict: str,
    summary: str,
) -> dict[str, object]:
    """Submit a review report for an assignment."""
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
        if assignment["status"] != "assigned":
            raise ValueError("STATE_TRANSITION_INVALID")

        await db.execute(
            """INSERT INTO review_reports
               (id, company_id, assignment_id, reviewer_run_id,
                verdict, report_artifact_id, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                report_id,
                company_id,
                assignment_id,
                None,
                verdict,
                report_artifact_id,
                now,
            ),
        )

        await db.execute(
            """UPDATE review_assignments
               SET status='submitted', submitted_at=?
               WHERE id=? AND company_id=?""",
            (now, assignment_id, company_id),
        )

        await db.commit()
        return {
            "id": report_id,
            "assignment_id": assignment_id,
            "verdict": verdict,
            "status": "completed",
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
    description: str,
    file_path: str | None = None,
    line_number: int | None = None,
) -> dict[str, object]:
    """Create an issue from a review report."""
    issue_id = _id()
    now = _now()

    await db.execute(
        """INSERT INTO review_issues
           (id, company_id, review_report_id, severity, category,
            description, expected, actual, suggested_fix,
            evidence_refs_json, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            issue_id,
            company_id,
            report_id,
            severity,
            "",
            description,
            "",
            "",
            "",
            "[]",
            "open",
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


async def resolve_review_issue(
    db: Any,
    company_id: str,
    *,
    issue_id: str,
    resolution: str,
) -> dict[str, object]:
    """Resolve a review issue."""
    now = _now()

    cursor = await db.execute(
        """UPDATE review_issues
           SET status='resolved', rejection_reason=?,
               updated_at=?, version=version+1
           WHERE id=? AND company_id=? AND status='open'""",
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
