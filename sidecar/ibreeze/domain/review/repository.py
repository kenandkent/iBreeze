from __future__ import annotations

import json
import uuid
from typing import Any, Literal
from uuid import UUID

from ibreeze.domain.review.entities import ReviewAssignment, ReviewIssue, ReviewReport
from ibreeze.domain.review.state import ASSIGNMENT_TRANSITIONS, ISSUE_TRANSITIONS


class ReviewRepository:

    async def lock_assignment(
        self,
        session: Any,
        assignment_id: UUID,
    ) -> ReviewAssignment:
        cursor = await session.execute(
            """SELECT id, company_id, artifact_id, reviewed_sha256,
                      reviewer_employee_id, status, version
               FROM review_assignments
               WHERE id=?""",
            (str(assignment_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        return ReviewAssignment(
            id=UUID(row["id"]),
            company_id=UUID(row["company_id"]),
            artifact_id=UUID(row["artifact_id"]),
            artifact_sha256=row["reviewed_sha256"],
            reviewer_employee_id=UUID(row["reviewer_employee_id"]),
            state=row["status"],
            version=row["version"],
        )

    async def lock_issue(
        self,
        session: Any,
        issue_id: UUID,
    ) -> ReviewIssue:
        cursor = await session.execute(
            """SELECT id, company_id, severity, category, status, version
               FROM review_issues
               WHERE id=?""",
            (str(issue_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        return ReviewIssue(
            id=UUID(row["id"]),
            company_id=UUID(row["company_id"]),
            severity=row["severity"],
            category=row["category"],
            state=row["status"],
            version=row["version"],
        )

    async def transition(
        self,
        session: Any,
        assignment: ReviewAssignment,
        target_state: str,
    ) -> ReviewAssignment:
        allowed = ASSIGNMENT_TRANSITIONS.get(assignment.state, frozenset())
        if target_state not in allowed:
            raise ValueError("STATE_TRANSITION_INVALID")
        cursor = await session.execute(
            """UPDATE review_assignments
               SET status=?, version=version+1
               WHERE id=? AND version=?""",
            (target_state, str(assignment.id), assignment.version),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        return ReviewAssignment(
            id=assignment.id,
            company_id=assignment.company_id,
            artifact_id=assignment.artifact_id,
            artifact_sha256=assignment.artifact_sha256,
            reviewer_employee_id=assignment.reviewer_employee_id,
            state=target_state,
            version=assignment.version + 1,
        )

    async def transition_issue(
        self,
        session: Any,
        issue: ReviewIssue,
        target_state: str,
    ) -> ReviewIssue:
        allowed = ISSUE_TRANSITIONS.get(issue.state, frozenset())
        if target_state not in allowed:
            raise ValueError("STATE_TRANSITION_INVALID")
        if target_state == "rejected" and issue.severity in ("blocker", "high"):
            raise ValueError("BLOCKER_HIGH_CANNOT_BE_REJECTED")
        cursor = await session.execute(
            """UPDATE review_issues
               SET status=?, version=version+1, updated_at=datetime('now')
               WHERE id=? AND version=?""",
            (target_state, str(issue.id), issue.version),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        return ReviewIssue(
            id=issue.id,
            company_id=issue.company_id,
            severity=issue.severity,
            category=issue.category,
            state=target_state,
            version=issue.version + 1,
        )

    async def create_report(
        self,
        session: Any,
        company_id: UUID,
        assignment_id: UUID,
        reviewer_run_id: UUID,
        reviewed_artifact_id: UUID,
        reviewed_sha256: str,
        verdict: Literal["pass", "needs_changes", "failed"],
        report_artifact_id: UUID,
    ) -> ReviewReport:
        report_id = str(uuid.uuid4())
        await session.execute(
            """INSERT INTO review_reports
               (id, company_id, assignment_id, reviewer_run_id,
                reviewed_artifact_id, reviewed_sha256, verdict,
                report_artifact_id, version)
               VALUES (?,?,?,?,?,?,?,?,1)""",
            (
                report_id,
                str(company_id),
                str(assignment_id),
                str(reviewer_run_id),
                str(reviewed_artifact_id),
                reviewed_sha256,
                verdict,
                str(report_artifact_id),
            ),
        )
        return ReviewReport(
            id=UUID(report_id),
            company_id=company_id,
            assignment_id=assignment_id,
            reviewer_run_id=reviewer_run_id,
            reviewed_artifact_id=reviewed_artifact_id,
            reviewed_sha256=reviewed_sha256,
            verdict=verdict,
            version=1,
        )

    async def create_issues(
        self,
        session: Any,
        company_id: UUID,
        report_id: UUID,
        issues: list[dict[str, Any]],
    ) -> tuple[ReviewIssue, ...]:
        result: list[ReviewIssue] = []
        for iss in issues:
            issue_id = str(uuid.uuid4())
            evidence_json = json.dumps(
                [str(ref) for ref in iss.get("evidence_refs", [])],
                separators=(",", ":"),
            )
            await session.execute(
                """INSERT INTO review_issues
                   (id, company_id, review_report_id, severity, category,
                    description, expected, actual, suggested_fix,
                    evidence_refs_json, status, assignee_employee_id,
                    created_at, updated_at, version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),1)""",
                (
                    issue_id,
                    str(company_id),
                    str(report_id),
                    iss["severity"],
                    iss["category"],
                    iss.get("description", ""),
                    iss.get("expected", ""),
                    iss.get("actual", ""),
                    iss.get("suggested_fix", ""),
                    evidence_json,
                    "open",
                    str(iss.get("assignee_employee_id")) if iss.get("assignee_employee_id") else None,
                ),
            )
            result.append(ReviewIssue(
                id=UUID(issue_id),
                company_id=company_id,
                severity=iss["severity"],
                category=iss["category"],
                state="open",
                version=1,
            ))
        return tuple(result)

    async def stale_assignments_for_hash(
        self,
        session: Any,
        artifact_sha256: str,
    ) -> list[ReviewAssignment]:
        cursor = await session.execute(
            """SELECT id, company_id, artifact_id, reviewed_sha256,
                      reviewer_employee_id, status, version
               FROM review_assignments
               WHERE reviewed_sha256=? AND status NOT IN ('stale','cancelled')""",
            (artifact_sha256,),
        )
        rows = await cursor.fetchall()
        return [
            ReviewAssignment(
                id=UUID(row["id"]),
                company_id=UUID(row["company_id"]),
                artifact_id=UUID(row["artifact_id"]),
                artifact_sha256=row["reviewed_sha256"],
                reviewer_employee_id=UUID(row["reviewer_employee_id"]),
                state=row["status"],
                version=row["version"],
            )
            for row in rows
        ]
