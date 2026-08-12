from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from ibreeze.domain.review.commands import (
    CloseIssue,
    RejectIssue,
    RerunReview,
    ResolveIssue,
    StartIssueFix,
    StartReview,
    SubmitReview,
    VerifyIssue,
)
from ibreeze.domain.review.entities import ReviewAssignment
from ibreeze.domain.review.repository import ReviewRepository
from ibreeze.persistence.types import DomainEventRecord, OutboxRecord
from ibreeze.persistence.unit_of_work import CommandResult


def canonical_hash(request: Any) -> str:
    raw = json.dumps(
        asdict(cast(Any, request)) if is_dataclass(request) else request,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _event(
    event_type: str,
    aggregate_type: str,
    aggregate_id: Any,
    aggregate_version: int,
    company_id: Any,
    payload: dict[str, Any],
) -> DomainEventRecord:
    return DomainEventRecord(
        event_id=uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=UUID(str(aggregate_id)),
        aggregate_version=aggregate_version,
        company_id=UUID(str(company_id)) if company_id is not None else None,
        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        trace_id=str(uuid4()),
    )


def _outbox(topic: str, payload: dict[str, Any], event: DomainEventRecord) -> OutboxRecord:
    return OutboxRecord(
        topic=topic,
        payload_json=event.payload_json,
        domain_event_id=event.event_id,
    )


def _issue_event_payload(previous: Any, result: Any) -> dict[str, Any]:
    """Return the closed event payload required by review.issue_changed.v1."""
    return {
        "company_id": str(result.company_id),
        "aggregate_id": str(result.id),
        "version": result.version,
        "issue_id": str(result.id),
        "from_state": previous.state,
        "to_state": result.state,
        "severity": result.severity,
        "assignee_employee_id": (
            str(result.assignee_employee_id) if result.assignee_employee_id else None
        ),
        "verifier_employee_id": (
            str(result.verifier_employee_id) if result.verifier_employee_id else None
        ),
        "rejection_reason": result.rejection_reason,
        "evidence_refs": list(result.evidence_refs),
    }


class SubmitReviewGuards:
    def __init__(self, repo: ReviewRepository) -> None:
        self._repo = repo

    async def validate(
        self,
        session: Any,
        assignment: ReviewAssignment,
        request: SubmitReview,
    ) -> None:
        if assignment.company_id != request.company_id:
            raise ValueError("COMPANY_SCOPE_MISMATCH")
        if assignment.state not in ("assigned", "in_review"):
            raise ValueError("STATE_TRANSITION_INVALID")
        if request.expected_assignment_version != assignment.version:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        if request.reviewed_artifact_id != assignment.artifact_id:
            raise ValueError("REVIEW_ARTIFACT_MISMATCH")
        if request.reviewed_sha256 != assignment.artifact_sha256:
            raise ValueError("REVIEW_HASH_MISMATCH")

        cursor = await session.execute(
            """SELECT employee_id, run_purpose, status, company_id
               FROM agent_runs WHERE id=?""",
            (str(request.reviewer_run_id),),
        )
        run = await cursor.fetchone()
        if run is None or run["company_id"] != str(request.company_id):
            raise ValueError("REVIEW_RUN_SCOPE_MISMATCH")
        if run["run_purpose"] != "review" or run["employee_id"] != str(assignment.reviewer_employee_id):
            raise ValueError("REVIEW_RUN_BINDING_MISMATCH")
        if run["status"] != "succeeded":
            raise ValueError("REVIEW_RUN_NOT_COMPLETE")

        cursor = await session.execute(
            """SELECT object_sha256, is_current, company_id
               FROM artifacts WHERE id=?""",
            (str(request.reviewed_artifact_id),),
        )
        artifact = await cursor.fetchone()
        if (
            artifact is None
            or artifact["company_id"] != str(request.company_id)
            or int(artifact["is_current"]) != 1
            or artifact["object_sha256"] != request.reviewed_sha256
        ):
            raise ValueError("REVIEWED_ARTIFACT_NOT_CURRENT")

        cursor = await session.execute(
            """SELECT artifact_type, company_id, created_by_type, created_by_run_id
               FROM artifacts WHERE id=?""",
            (str(request.report_artifact_id),),
        )
        report_artifact = await cursor.fetchone()
        if (
            report_artifact is None
            or report_artifact["company_id"] != str(request.company_id)
            or report_artifact["artifact_type"] != "review_report"
            or report_artifact["created_by_type"] != "agent"
            or report_artifact["created_by_run_id"] != str(request.reviewer_run_id)
        ):
            raise ValueError("REVIEW_REPORT_ARTIFACT_MISMATCH")

        cursor = await session.execute(
            """SELECT 1 FROM artifact_contributors
               WHERE artifact_id=? AND company_id=? AND employee_id=?""",
            (str(assignment.artifact_id), str(assignment.company_id), str(assignment.reviewer_employee_id)),
        )
        if await cursor.fetchone() is not None:
            raise ValueError("REVIEW_SELF_ASSIGNMENT")
        for issue in request.issues:
            if issue.assignee_employee_id is not None:
                cursor = await session.execute(
                    "SELECT 1 FROM employees WHERE id=? AND company_id=? AND status='active'",
                    (str(issue.assignee_employee_id), str(request.company_id)),
                )
                if await cursor.fetchone() is None:
                    raise ValueError("REVIEW_ISSUE_ASSIGNEE_INVALID")
            if not issue.evidence_refs:
                raise ValueError("REVIEW_ISSUE_EVIDENCE_REQUIRED")
            for evidence_ref in issue.evidence_refs:
                cursor = await session.execute(
                    "SELECT 1 FROM artifacts WHERE id=? AND company_id=?",
                    (str(evidence_ref), str(request.company_id)),
                )
                if await cursor.fetchone() is None:
                    raise ValueError("REVIEW_ISSUE_EVIDENCE_NOT_FOUND")
        if request.verdict == "pass" and request.issues:
            raise ValueError("VERDICT_PASS_WITH_ISSUES")
        if request.verdict == "needs_changes" and not request.issues:
            raise ValueError("VERDICT_NEEDS_CHANGES_WITHOUT_ISSUES")
        if request.verdict == "failed":
            has_blocker_review_exec = any(
                iss.severity == "blocker" and iss.category == "review_execution" for iss in request.issues
            )
            if not has_blocker_review_exec:
                raise ValueError("VERDICT_FAILED_MISSING_BLOCKER_REVIEW_EXECUTION")


class StartReviewHandler:
    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: StartReview) -> Any:
        async def command(session: Any) -> Any:
            assignment = await self._repo.lock_assignment(
                session, request.assignment_id, request.company_id
            )
            if assignment.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition(session, assignment, "in_review")
            return CommandResult(
                response={"id": str(result.id), "status": result.state},
                events=(),
                outbox=(),
            )

        return await self._uow.execute(context, canonical_hash(request), command)


class SubmitReviewHandler:
    def __init__(
        self,
        repo: ReviewRepository,
        guards: SubmitReviewGuards,
        uow: Any,
        aggregation: Any | None = None,
    ) -> None:
        self._repo = repo
        self._guards = guards
        self._uow = uow
        self._aggregation = aggregation

    async def handle(self, context: Any, request: SubmitReview) -> Any:
        async def command(session: Any) -> Any:
            assignment = await self._repo.lock_assignment(
                session, request.assignment_id, request.company_id
            )
            await self._guards.validate(session, assignment, request)
            report = await self._repo.create_report(
                session,
                company_id=request.company_id,
                assignment_id=request.assignment_id,
                reviewer_run_id=request.reviewer_run_id,
                reviewed_artifact_id=request.reviewed_artifact_id,
                reviewed_sha256=request.reviewed_sha256,
                verdict=request.verdict,
                report_artifact_id=request.report_artifact_id,
            )
            issues_data = [
                {
                    "client_issue_id": str(iss.client_issue_id),
                    "severity": iss.severity,
                    "category": iss.category,
                    "description": iss.description,
                    "expected": iss.expected,
                    "actual": iss.actual,
                    "evidence_refs": iss.evidence_refs,
                    "suggested_fix": iss.suggested_fix,
                    "assignee_employee_id": iss.assignee_employee_id,
                }
                for iss in request.issues
            ]
            await self._repo.create_issues(session, request.company_id, report.id, issues_data)
            result = await self._repo.transition(session, assignment, "submitted")
            rerun_event: DomainEventRecord | None = None
            rerun_outbox: OutboxRecord | None = None
            if self._aggregation is not None:
                # Fuse verdicts + optional auto-rerun inside the same txn.  Any
                # round+1 review.assigned event the aggregation produced is
                # persisted here, atomic with the report.
                outcome = await self._aggregation.on_report_submitted(
                    session, company_id=request.company_id, assignment=result
                )
                rerun_event = outcome.rerun_event
                rerun_outbox = outcome.rerun_outbox
            payload = {
                "company_id": str(request.company_id),
                "aggregate_id": str(result.id),
                "version": result.version,
                "assignment_id": str(result.id),
                "reviewer_employee_id": str(result.reviewer_employee_id),
                "verdict": request.verdict,
            }
            event = _event(
                "review.submitted", "review_assignment", result.id, result.version,
                request.company_id,
                payload,
            )
            events: tuple[DomainEventRecord, ...] = (event,)
            outbox: tuple[OutboxRecord, ...] = (_outbox("review.submitted", payload, event),)
            if rerun_event is not None and rerun_outbox is not None:
                events = events + (rerun_event,)
                outbox = outbox + (rerun_outbox,)
            return CommandResult(
                response={"review_id": str(report.id)},
                events=events,
                outbox=outbox,
            )

        return await self._uow.execute(context, canonical_hash(request), command)


class RerunReviewHandler:
    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: RerunReview) -> Any:
        async def command(session: Any) -> Any:
            _assignment, event, outbox = await self._repo.create_rerun_assignment(
                session, request.company_id, request.review_id
            )
            return CommandResult(
                response={"status": "queued"},
                events=(event,),
                outbox=(outbox,),
            )

        return await self._uow.execute(context, canonical_hash(request), command)


class StartIssueFixHandler:
    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: StartIssueFix) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id, request.company_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(session, issue, "fixing")
            payload = _issue_event_payload(issue, result)
            event = _event(
                "review.issue_changed", "review_issue", result.id, result.version,
                getattr(result, "company_id", None),
                payload,
            )
            return CommandResult(
                response={"success": True},
                events=(event,),
                outbox=(_outbox("review.issue_changed", payload, event),),
            )

        return await self._uow.execute(context, canonical_hash(request), command)


class ResolveIssueHandler:
    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: ResolveIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id, request.company_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.resolve_issue_with_evidence(
                session,
                issue,
                resolution_artifact_sha256=request.resolution_artifact_sha256,
                fix_run_id=request.fix_run_id,
                retest_result_id=request.retest_result_id,
                resolution_summary=request.resolution_summary,
                expected_version=request.expected_version,
            )
            payload = _issue_event_payload(issue, result)
            event = _event(
                "review.issue_changed", "review_issue", result.id, result.version,
                getattr(result, "company_id", None),
                payload,
            )
            return CommandResult(
                response={"success": True},
                events=(event,),
                outbox=(_outbox("review.issue_changed", payload, event),),
            )

        return await self._uow.execute(context, canonical_hash(request), command)


class VerifyIssueHandler:
    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: VerifyIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id, request.company_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(
                session,
                issue,
                "verified",
                verifier_employee_id=request.verifier_employee_id,
            )
            payload = _issue_event_payload(issue, result)
            event = _event(
                "review.issue_changed", "review_issue", result.id, result.version,
                getattr(result, "company_id", None),
                payload,
            )
            return CommandResult(
                response={"id": str(result.id), "state": result.state},
                events=(event,),
                outbox=(_outbox("review.issue_changed", payload, event),),
            )

        return await self._uow.execute(context, canonical_hash(request), command)


class CloseIssueHandler:
    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: CloseIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id, request.company_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(session, issue, "closed")
            payload = _issue_event_payload(issue, result)
            event = _event(
                "review.issue_changed", "review_issue", result.id, result.version,
                getattr(result, "company_id", None),
                payload,
            )
            return CommandResult(
                response={"id": str(result.id), "state": result.state},
                events=(event,),
                outbox=(_outbox("review.issue_changed", payload, event),),
            )

        return await self._uow.execute(context, canonical_hash(request), command)


class RejectIssueHandler:
    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: RejectIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id, request.company_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(
                session,
                issue,
                "rejected",
                rejection_reason=request.rejection_reason,
            )
            payload = _issue_event_payload(issue, result)
            event = _event(
                "review.issue_changed", "review_issue", result.id, result.version,
                getattr(result, "company_id", None),
                payload,
            )
            return CommandResult(
                response={"id": str(result.id), "state": result.state},
                events=(event,),
                outbox=(_outbox("review.issue_changed", payload, event),),
            )

        return await self._uow.execute(context, canonical_hash(request), command)
