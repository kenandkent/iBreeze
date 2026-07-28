from __future__ import annotations

import hashlib
import json
from typing import Any

from ibreeze.domain.review.commands import (
    CloseIssue,
    RejectIssue,
    ResolveIssue,
    StartIssueFix,
    StartReview,
    SubmitReview,
    VerifyIssue,
)
from ibreeze.domain.review.entities import ReviewAssignment
from ibreeze.domain.review.repository import ReviewRepository
from ibreeze.persistence.unit_of_work import CommandResult


def canonical_hash(request: Any) -> str:
    raw = json.dumps(request, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class SubmitReviewGuards:

    def __init__(self, repo: ReviewRepository) -> None:
        self._repo = repo

    async def validate(
        self,
        session: Any,
        assignment: ReviewAssignment,
        request: SubmitReview,
    ) -> None:
        if assignment.state not in ("assigned", "in_review"):
            raise ValueError("STATE_TRANSITION_INVALID")
        if request.expected_assignment_version != assignment.version:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        cursor = await session.execute(
            """SELECT 1 FROM artifact_contributors
               WHERE artifact_id=? AND company_id=? AND employee_id=?""",
            (str(assignment.artifact_id), str(assignment.company_id),
             str(assignment.reviewer_employee_id)),
        )
        if await cursor.fetchone() is not None:
            raise ValueError("REVIEW_SELF_ASSIGNMENT")
        if request.verdict == "pass" and request.issues:
            raise ValueError("VERDICT_PASS_WITH_ISSUES")
        if request.verdict == "needs_changes" and not request.issues:
            raise ValueError("VERDICT_NEEDS_CHANGES_WITHOUT_ISSUES")
        if request.verdict == "failed":
            has_blocker_review_exec = any(
                iss.severity == "blocker" and iss.category == "review_execution"
                for iss in request.issues
            )
            if not has_blocker_review_exec:
                raise ValueError("VERDICT_FAILED_MISSING_BLOCKER_REVIEW_EXECUTION")


class StartReviewHandler:

    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: StartReview) -> Any:
        async def command(session: Any) -> Any:
            assignment = await self._repo.lock_assignment(session, request.assignment_id)
            if assignment.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition(session, assignment, "in_review")
            return CommandResult(
                response={"id": str(result.id), "status": result.state},
                events=({
                    "event_type": "review.assigned",
                    "aggregate_id": str(result.id),
                    "from_state": assignment.state,
                    "to_state": result.state,
                    "version": result.version,
                },),
                outbox=(),
            )
        return await self._uow.execute(context, canonical_hash(request), command)


class SubmitReviewHandler:

    def __init__(
        self,
        repo: ReviewRepository,
        guards: SubmitReviewGuards,
        uow: Any,
    ) -> None:
        self._repo = repo
        self._guards = guards
        self._uow = uow

    async def handle(self, context: Any, request: SubmitReview) -> Any:
        async def command(session: Any) -> Any:
            assignment = await self._repo.lock_assignment(
                session, request.assignment_id
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
            issues = await self._repo.create_issues(
                session, request.company_id, report.id, issues_data
            )
            result = await self._repo.transition(session, assignment, "submitted")
            return CommandResult(
                response={
                    "assignment": {
                        "id": str(result.id),
                        "state": result.state,
                        "version": result.version,
                    },
                    "report": {
                        "id": str(report.id),
                        "verdict": report.verdict,
                    },
                    "issues": [
                        {"id": str(iss.id), "severity": iss.severity, "state": iss.state}
                        for iss in issues
                    ],
                },
                events=({
                    "event_type": "review.submitted",
                    "aggregate_id": str(result.id),
                    "aggregate_type": "review_assignment",
                    "from_state": assignment.state,
                    "to_state": result.state,
                    "version": result.version,
                    "company_id": str(request.company_id),
                },),
                outbox=({
                    "command_type": "EvaluateEmployeeAcceptance",
                    "payload": {
                        "assignment_id": str(result.id),
                        "company_id": str(request.company_id),
                    },
                },),
            )
        return await self._uow.execute(context, canonical_hash(request), command)


class StartIssueFixHandler:

    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: StartIssueFix) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(
                session, issue, "fixing"
            )
            return CommandResult(
                response={"id": str(result.id), "state": result.state},
                events=({
                    "event_type": "review.issue_changed",
                    "issue_id": str(result.id),
                    "from_state": issue.state,
                    "to_state": result.state,
                    "severity": result.severity,
                },),
                outbox=(),
            )
        return await self._uow.execute(context, canonical_hash(request), command)


class ResolveIssueHandler:

    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: ResolveIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(
                session, issue, "resolved"
            )
            return CommandResult(
                response={"id": str(result.id), "state": result.state},
                events=({
                    "event_type": "review.issue_changed",
                    "issue_id": str(result.id),
                    "from_state": issue.state,
                    "to_state": result.state,
                    "severity": result.severity,
                },),
                outbox=(),
            )
        return await self._uow.execute(context, canonical_hash(request), command)


class VerifyIssueHandler:

    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: VerifyIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(
                session, issue, "verified"
            )
            return {
                "response": {"id": str(result.id), "state": result.state},
                "events": ({
                    "event_type": "review.issue_changed",
                    "issue_id": str(result.id),
                    "from_state": issue.state,
                    "to_state": result.state,
                    "severity": result.severity,
                },),
                "outbox": (),
            }
        return await self._uow.execute(context, canonical_hash(request), command)


class CloseIssueHandler:

    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: CloseIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(
                session, issue, "closed"
            )
            return CommandResult(
                response={"id": str(result.id), "state": result.state},
                events=({
                    "event_type": "review.issue_changed",
                    "issue_id": str(result.id),
                    "from_state": issue.state,
                    "to_state": result.state,
                    "severity": result.severity,
                },),
                outbox=({
                    "command_type": "EvaluateAffectedTask",
                    "payload": {
                        "issue_id": str(result.id),
                        "company_id": str(result.company_id),
                    },
                },),
            )
        return await self._uow.execute(context, canonical_hash(request), command)


class RejectIssueHandler:

    def __init__(self, repo: ReviewRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, context: Any, request: RejectIssue) -> Any:
        async def command(session: Any) -> Any:
            issue = await self._repo.lock_issue(session, request.issue_id)
            if issue.version != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            result = await self._repo.transition_issue(
                session, issue, "rejected"
            )
            return CommandResult(
                response={"id": str(result.id), "state": result.state},
                events=({
                    "event_type": "review.issue_changed",
                    "issue_id": str(result.id),
                    "from_state": issue.state,
                    "to_state": result.state,
                    "severity": result.severity,
                },),
                outbox=(),
            )
        return await self._uow.execute(context, canonical_hash(request), command)
