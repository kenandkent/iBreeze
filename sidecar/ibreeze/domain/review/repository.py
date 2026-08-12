from __future__ import annotations

import json
import uuid
from typing import Any, Literal
from uuid import UUID

from ibreeze.domain.review.entities import ReviewAssignment, ReviewIssue, ReviewReport
from ibreeze.domain.review.state import ASSIGNMENT_TRANSITIONS, ISSUE_TRANSITIONS
from ibreeze.persistence.types import DomainEventRecord, OutboxRecord


class ReviewRepository:
    async def create_rerun_assignment(
        self,
        session: Any,
        company_id: UUID,
        review_id: UUID,
    ) -> tuple[ReviewAssignment, DomainEventRecord, OutboxRecord]:
        """Create the next review assignment in the canonical write path.

        A rerun is a new aggregate instance.  The previous report remains
        immutable audit evidence; only a current artifact may be assigned and
        the assignment plus ``review.assigned`` event/outbox rows are written
        by the surrounding UnitOfWork transaction.
        """
        cursor = await session.execute(
            """SELECT rr.company_id, ra.artifact_id, ra.reviewer_employee_id,
                      ra.review_round, ra.reviewed_sha256
               FROM review_reports rr
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               WHERE rr.id=? AND rr.company_id=?""",
            (str(review_id), str(company_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")

        artifact = await (
            await session.execute(
                """SELECT object_sha256, is_current
                   FROM artifacts WHERE id=? AND company_id=?""",
                (row["artifact_id"], str(company_id)),
            )
        ).fetchone()
        if artifact is None or int(artifact["is_current"]) != 1:
            raise ValueError("REVIEW_STALE_ARTIFACT")
        if artifact["object_sha256"] != row["reviewed_sha256"]:
            raise ValueError("REVIEW_HASH_MISMATCH")

        reviewer = await (
            await session.execute(
                """SELECT 1 FROM employees
                   WHERE id=? AND company_id=? AND status='active'""",
                (row["reviewer_employee_id"], str(company_id)),
            )
        ).fetchone()
        if reviewer is None:
            raise ValueError("REVIEWER_NOT_AVAILABLE")
        contributor = await (
            await session.execute(
                """SELECT 1 FROM artifact_contributors
                   WHERE artifact_id=? AND company_id=? AND employee_id=?""",
                (row["artifact_id"], str(company_id), row["reviewer_employee_id"]),
            )
        ).fetchone()
        if contributor is not None:
            raise ValueError("REVIEWER_CANNOT_BE_CONTRIBUTOR")

        assignment_id = UUID(str(uuid.uuid4()))
        review_round = int(row["review_round"]) + 1
        await session.execute(
            """INSERT INTO review_assignments
               (id, company_id, artifact_id, reviewer_employee_id,
                review_round, reviewed_sha256, status, assigned_at)
               VALUES (?,?,?,?,?,?, 'assigned', strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
            (
                str(assignment_id),
                str(company_id),
                row["artifact_id"],
                row["reviewer_employee_id"],
                review_round,
                row["reviewed_sha256"],
            ),
        )
        assignment = ReviewAssignment(
            id=assignment_id,
            company_id=company_id,
            artifact_id=UUID(str(row["artifact_id"])),
            artifact_sha256=row["reviewed_sha256"],
            reviewer_employee_id=UUID(str(row["reviewer_employee_id"])),
            state="assigned",
            version=1,
        )
        payload = {
            "company_id": str(company_id),
            "aggregate_id": str(assignment_id),
            "version": 1,
            "assignment_id": str(assignment_id),
            "reviewer_employee_id": str(assignment.reviewer_employee_id),
        }
        event_id = UUID(str(uuid.uuid4()))
        event = DomainEventRecord(
            event_id=event_id,
            event_type="review.assigned",
            aggregate_type="review_assignment",
            aggregate_id=assignment_id,
            aggregate_version=1,
            company_id=company_id,
            payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            trace_id=str(uuid.uuid4()),
        )
        outbox = OutboxRecord(
            topic="review.assigned",
            payload_json=event.payload_json,
            domain_event_id=event_id,
        )
        return assignment, event, outbox

    async def lock_assignment(
        self,
        session: Any,
        assignment_id: UUID,
        company_id: UUID,
    ) -> ReviewAssignment:
        cursor = await session.execute(
            """SELECT id, company_id, artifact_id, reviewed_sha256,
                      reviewer_employee_id, status, version
               FROM review_assignments
               WHERE id=? AND company_id=?""",
            (str(assignment_id), str(company_id)),
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
        company_id: UUID,
    ) -> ReviewIssue:
        cursor = await session.execute(
            """SELECT id, company_id, severity, category, status, version,
                      assignee_employee_id, verifier_employee_id,
                      rejection_reason, evidence_refs_json
               FROM review_issues
               WHERE id=? AND company_id=?""",
            (str(issue_id), str(company_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        try:
            evidence_refs = tuple(json.loads(row["evidence_refs_json"] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("REVIEW_ISSUE_EVIDENCE_INVALID") from None
        return ReviewIssue(
            id=UUID(row["id"]),
            company_id=UUID(row["company_id"]),
            severity=row["severity"],
            category=row["category"],
            state=row["status"],
            version=row["version"],
            assignee_employee_id=(UUID(row["assignee_employee_id"]) if row["assignee_employee_id"] else None),
            evidence_refs=evidence_refs,
            verifier_employee_id=(
                UUID(row["verifier_employee_id"]) if row["verifier_employee_id"] else None
            ),
            rejection_reason=row["rejection_reason"],
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
               SET status=?,
                   submitted_at=CASE WHEN ?='submitted'
                       THEN strftime('%Y-%m-%dT%H:%M:%fZ','now')
                       ELSE submitted_at END,
                   version=version+1
               WHERE id=? AND company_id=? AND version=?""",
            (
                target_state,
                target_state,
                str(assignment.id),
                str(assignment.company_id),
                assignment.version,
            ),
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
        *,
        verifier_employee_id: UUID | None = None,
        rejection_reason: str | None = None,
    ) -> ReviewIssue:
        allowed = ISSUE_TRANSITIONS.get(issue.state, frozenset())
        if target_state not in allowed:
            raise ValueError("STATE_TRANSITION_INVALID")
        if target_state == "rejected" and issue.severity in ("blocker", "high"):
            raise ValueError("BLOCKER_HIGH_CANNOT_BE_REJECTED")
        if target_state == "rejected":
            reason = (rejection_reason or "").strip()
            if not reason or len(reason) > 2_000:
                raise ValueError("REJECTION_REASON_REQUIRED")
        if target_state == "verified":
            if verifier_employee_id is None:
                raise ValueError("VERIFIER_REQUIRED")
            cursor = await session.execute(
                """SELECT 1 FROM employees
                   WHERE id=? AND company_id=? AND status='active'""",
                (str(verifier_employee_id), str(issue.company_id)),
            )
            if await cursor.fetchone() is None:
                raise ValueError("VERIFIER_NOT_AVAILABLE")
        elif verifier_employee_id is not None:
            raise ValueError("VERIFIER_NOT_ALLOWED")
        cursor = await session.execute(
            """UPDATE review_issues
               SET status=?, version=version+1, updated_at=datetime('now'),
                   verifier_employee_id=CASE WHEN ?='verified' THEN ? ELSE verifier_employee_id END,
                   rejection_reason=CASE WHEN ?='rejected' THEN ? ELSE rejection_reason END
               WHERE id=? AND company_id=? AND version=?""",
            (
                target_state,
                target_state,
                str(verifier_employee_id) if verifier_employee_id else None,
                target_state,
                (rejection_reason or "").strip() if target_state == "rejected" else None,
                str(issue.id),
                str(issue.company_id),
                issue.version,
            ),
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
            assignee_employee_id=issue.assignee_employee_id,
            evidence_refs=issue.evidence_refs,
            verifier_employee_id=(
                verifier_employee_id if target_state == "verified" else issue.verifier_employee_id
            ),
            rejection_reason=(
                (rejection_reason or "").strip()
                if target_state == "rejected"
                else issue.rejection_reason
            ),
        )

    async def resolve_issue_with_evidence(
        self,
        session: Any,
        issue: ReviewIssue,
        *,
        resolution_artifact_sha256: str,
        fix_run_id: UUID,
        retest_result_id: UUID,
        resolution_summary: str,
        expected_version: int,
    ) -> ReviewIssue:
        """Resolve a fixing issue only after binding executable evidence."""
        if issue.state != "fixing":
            raise ValueError("STATE_TRANSITION_INVALID")
        if issue.version != expected_version:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        if len(resolution_artifact_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in resolution_artifact_sha256
        ):
            raise ValueError("RESOLUTION_ARTIFACT_HASH_INVALID")
        if not 1 <= len(resolution_summary) <= 20_000:
            raise ValueError("RESOLUTION_SUMMARY_INVALID")

        artifact_cursor = await session.execute(
            """SELECT id FROM artifacts
               WHERE company_id=? AND object_sha256=? AND is_current=1""",
            (str(issue.company_id), resolution_artifact_sha256),
        )
        if await artifact_cursor.fetchone() is None:
            raise ValueError("RESOLUTION_ARTIFACT_NOT_FOUND")

        run_cursor = await session.execute(
            """SELECT id FROM agent_runs
               WHERE id=? AND company_id=? AND run_purpose='repair'
                 AND status='succeeded'""",
            (str(fix_run_id), str(issue.company_id)),
        )
        if await run_cursor.fetchone() is None:
            raise ValueError("FIX_RUN_NOT_COMPLETE")

        retest_cursor = await session.execute(
            """SELECT id FROM artifacts
               WHERE id=? AND company_id=? AND artifact_type='test_result'
                 AND is_current=1""",
            (str(retest_result_id), str(issue.company_id)),
        )
        if await retest_cursor.fetchone() is None:
            raise ValueError("RETEST_RESULT_NOT_FOUND")

        evidence = {
            "issue_id": str(issue.id),
            "resolution_artifact_sha256": resolution_artifact_sha256,
            "fix_run_id": str(fix_run_id),
            "retest_result_id": str(retest_result_id),
            "resolution_summary": resolution_summary,
        }
        await session.execute(
            """INSERT INTO resolution_evidence
               (id, company_id, issue_id, evidence_json, created_at)
               VALUES (?,?,?,?,datetime('now'))""",
            (
                str(uuid.uuid4()),
                str(issue.company_id),
                str(issue.id),
                json.dumps(evidence, sort_keys=True, separators=(",", ":")),
            ),
        )
        cursor = await session.execute(
            """UPDATE review_issues
               SET status='resolved', updated_at=datetime('now'), version=version+1
               WHERE id=? AND company_id=? AND status='fixing' AND version=?""",
            (
                str(issue.id),
                str(issue.company_id),
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        return ReviewIssue(
            id=issue.id,
            company_id=issue.company_id,
            severity=issue.severity,
            category=issue.category,
            state="resolved",
            version=expected_version + 1,
            assignee_employee_id=issue.assignee_employee_id,
            evidence_refs=issue.evidence_refs,
            verifier_employee_id=issue.verifier_employee_id,
            rejection_reason=issue.rejection_reason,
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
                report_artifact_id, created_at, version)
               VALUES (?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),1)""",
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
            result.append(
                ReviewIssue(
                    id=UUID(issue_id),
                    company_id=company_id,
                    severity=iss["severity"],
                    category=iss["category"],
                    state="open",
                    version=1,
                    assignee_employee_id=(
                        UUID(str(iss["assignee_employee_id"]))
                        if iss.get("assignee_employee_id")
                        else None
                    ),
                    evidence_refs=tuple(str(ref) for ref in iss.get("evidence_refs", [])),
                )
            )
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
