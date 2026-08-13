"""Cover review_handlers branches the main suite does not reach.

Targets: the real ``canonical_hash`` body, the ``_project_review_outcome``
no-op returns, the remaining ``SubmitReviewGuards`` error paths, and the
``RerunReviewHandler`` command.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest

from ibreeze.application.review_handlers import (
    RerunReviewHandler,
    SubmitReviewGuards,
    _project_review_outcome,
    canonical_hash,
)
from ibreeze.domain.review.commands import RerunReview, ReviewIssueInput, SubmitReview
from ibreeze.domain.review.entities import ReviewAssignment
from ibreeze.domain.review.repository import ReviewRepository
from ibreeze.persistence.unit_of_work import CommandResult

_UNSET = object()


def _fetchone_cursor(row):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=row)
    return cursor


def _make_assignment(**overrides) -> ReviewAssignment:
    return ReviewAssignment(
        id=overrides.get("id", uuid.uuid4()),
        company_id=overrides.get("company_id", uuid.uuid4()),
        artifact_id=overrides.get("artifact_id", uuid.uuid4()),
        artifact_sha256=overrides.get("artifact_sha256", "a" * 64),
        reviewer_employee_id=overrides.get("reviewer_employee_id", uuid.uuid4()),
        state=overrides.get("state", "assigned"),
        version=overrides.get("version", 1),
    )


def _request(assignment: ReviewAssignment, *, verdict: str = "pass", issues=()):
    return SubmitReview(
        company_id=assignment.company_id,
        assignment_id=assignment.id,
        reviewer_run_id=uuid.uuid4(),
        reviewed_artifact_id=assignment.artifact_id,
        reviewed_sha256=assignment.artifact_sha256,
        report_artifact_id=uuid.uuid4(),
        verdict=verdict,
        issues=issues,
        expected_assignment_version=assignment.version,
    )


def _issue(assignment: ReviewAssignment, *, evidence_refs=None, assignee=None, severity="high", category="functional"):
    return ReviewIssueInput(
        client_issue_id=uuid.uuid4(),
        severity=severity,
        category=category,
        description="test",
        expected="ok",
        actual="bad",
        evidence_refs=evidence_refs if evidence_refs is not None else (assignment.artifact_id,),
        suggested_fix="fix",
        assignee_employee_id=assignee,
    )


def _session(
    request: SubmitReview,
    reviewer_employee_id: UUID,
    *,
    run=_UNSET,
    artifact=_UNSET,
    report_artifact=_UNSET,
    contributor=False,
    employees=_UNSET,
    evidence=_UNSET,
) -> AsyncMock:
    """Session whose execute dispatches by SQL shape; defaults pass every check."""
    session = AsyncMock()

    async def execute(sql: str, _params=()):
        text = str(sql)
        if "FROM agent_runs" in text:
            row = (
                run
                if run is not _UNSET
                else {
                    "employee_id": str(reviewer_employee_id),
                    "run_purpose": "review",
                    "status": "succeeded",
                    "company_id": str(request.company_id),
                }
            )
        elif "object_sha256" in text:
            row = (
                artifact
                if artifact is not _UNSET
                else {
                    "object_sha256": request.reviewed_sha256,
                    "is_current": 1,
                    "company_id": str(request.company_id),
                }
            )
        elif "artifact_type" in text:
            row = (
                report_artifact
                if report_artifact is not _UNSET
                else {
                    "artifact_type": "review_report",
                    "company_id": str(request.company_id),
                    "created_by_type": "agent",
                    "created_by_run_id": str(request.reviewer_run_id),
                }
            )
        elif "artifact_contributors" in text:
            row = {"1": 1} if contributor else None
        elif "FROM employees" in text:
            row = employees if employees is not _UNSET else {"1": 1}
        elif "FROM artifacts" in text:
            row = evidence if evidence is not _UNSET else {"1": 1}
        else:
            row = None
        return _fetchone_cursor(row)

    session.execute = AsyncMock(side_effect=execute)
    return session


class TestCanonicalHash:
    def test_dataclass_request(self) -> None:
        digest = canonical_hash(RerunReview(company_id=uuid.uuid4(), review_id=uuid.uuid4()))
        assert isinstance(digest, str)
        assert len(digest) == 64
        int(digest, 16)

    def test_plain_dict_request(self) -> None:
        digest = canonical_hash({"method": "review.rerun", "review_id": str(uuid.uuid4())})
        assert len(digest) == 64


class TestProjectReviewOutcome:
    async def test_returns_when_no_route_decision(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        request = Mock(spec=SubmitReview, company_id=uuid.uuid4(), reviewer_run_id=uuid.uuid4(), verdict="pass", issues=())
        await _project_review_outcome(session, request, uuid.uuid4())
        session.execute.assert_awaited_once()

    async def test_returns_for_unknown_verdict(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor({"id": "rd-1"}))
        request = Mock(spec=SubmitReview, company_id=uuid.uuid4(), reviewer_run_id=uuid.uuid4(), verdict="weird", issues=())
        await _project_review_outcome(session, request, uuid.uuid4())
        session.execute.assert_awaited_once()


class TestSubmitReviewGuards:
    async def _raises(self, session, assignment, request, expected):
        with pytest.raises(ValueError, match=expected):
            await SubmitReviewGuards(Mock(spec=ReviewRepository)).validate(session, assignment, request)

    async def test_company_scope_mismatch(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment)
        request = SubmitReview(
            company_id=uuid.uuid4(),
            assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(),
            reviewed_artifact_id=assignment.artifact_id,
            reviewed_sha256=assignment.artifact_sha256,
            report_artifact_id=uuid.uuid4(),
            verdict="pass",
            issues=(),
            expected_assignment_version=assignment.version,
        )
        await self._raises(AsyncMock(), assignment, request, "COMPANY_SCOPE_MISMATCH")

    async def test_review_artifact_mismatch(self) -> None:
        assignment = _make_assignment()
        request = SubmitReview(
            company_id=assignment.company_id,
            assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(),
            reviewed_artifact_id=uuid.uuid4(),
            reviewed_sha256=assignment.artifact_sha256,
            report_artifact_id=uuid.uuid4(),
            verdict="pass",
            issues=(),
            expected_assignment_version=assignment.version,
        )
        await self._raises(AsyncMock(), assignment, request, "REVIEW_ARTIFACT_MISMATCH")

    async def test_review_hash_mismatch(self) -> None:
        assignment = _make_assignment()
        request = SubmitReview(
            company_id=assignment.company_id,
            assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(),
            reviewed_artifact_id=assignment.artifact_id,
            reviewed_sha256="b" * 64,
            report_artifact_id=uuid.uuid4(),
            verdict="pass",
            issues=(),
            expected_assignment_version=assignment.version,
        )
        await self._raises(AsyncMock(), assignment, request, "REVIEW_HASH_MISMATCH")

    async def test_run_scope_mismatch_when_run_missing(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment)
        await self._raises(_session(request, assignment.reviewer_employee_id, run=None), assignment, request, "REVIEW_RUN_SCOPE_MISMATCH")

    async def test_run_scope_mismatch_when_company_differs(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment)
        bad_run = {
            "employee_id": str(assignment.reviewer_employee_id),
            "run_purpose": "review",
            "status": "succeeded",
            "company_id": str(uuid.uuid4()),
        }
        await self._raises(_session(request, assignment.reviewer_employee_id, run=bad_run), assignment, request, "REVIEW_RUN_SCOPE_MISMATCH")

    async def test_run_binding_mismatch(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment)
        wrong_purpose = {
            "employee_id": str(assignment.reviewer_employee_id),
            "run_purpose": "probe",
            "status": "succeeded",
            "company_id": str(request.company_id),
        }
        await self._raises(
            _session(request, assignment.reviewer_employee_id, run=wrong_purpose), assignment, request, "REVIEW_RUN_BINDING_MISMATCH"
        )

    async def test_run_not_complete(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment)
        failed_run = {
            "employee_id": str(assignment.reviewer_employee_id),
            "run_purpose": "review",
            "status": "failed",
            "company_id": str(request.company_id),
        }
        await self._raises(_session(request, assignment.reviewer_employee_id, run=failed_run), assignment, request, "REVIEW_RUN_NOT_COMPLETE")

    async def test_reviewed_artifact_not_current(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment)
        stale = {
            "object_sha256": request.reviewed_sha256,
            "is_current": 0,
            "company_id": str(request.company_id),
        }
        await self._raises(_session(request, assignment.reviewer_employee_id, artifact=stale), assignment, request, "REVIEWED_ARTIFACT_NOT_CURRENT")

    async def test_report_artifact_mismatch(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment)
        wrong_report = {
            "artifact_type": "document",
            "company_id": str(request.company_id),
            "created_by_type": "agent",
            "created_by_run_id": str(request.reviewer_run_id),
        }
        await self._raises(
            _session(request, assignment.reviewer_employee_id, report_artifact=wrong_report), assignment, request, "REVIEW_REPORT_ARTIFACT_MISMATCH"
        )

    async def test_issue_assignee_invalid(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment, issues=(_issue(assignment, assignee=uuid.uuid4()),))
        await self._raises(
            _session(request, assignment.reviewer_employee_id, employees=None), assignment, request, "REVIEW_ISSUE_ASSIGNEE_INVALID"
        )

    async def test_issue_with_existing_assignee_falls_through(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment, verdict="needs_changes", issues=(_issue(assignment, assignee=uuid.uuid4()),))
        await SubmitReviewGuards(Mock(spec=ReviewRepository)).validate(_session(request, assignment.reviewer_employee_id), assignment, request)

    async def test_issue_evidence_required(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment, issues=(_issue(assignment, evidence_refs=(), assignee=None),))
        await self._raises(_session(request, assignment.reviewer_employee_id), assignment, request, "REVIEW_ISSUE_EVIDENCE_REQUIRED")

    async def test_issue_evidence_not_found(self) -> None:
        assignment = _make_assignment()
        request = _request(assignment, issues=(_issue(assignment, assignee=None),))
        await self._raises(_session(request, assignment.reviewer_employee_id, evidence=None), assignment, request, "REVIEW_ISSUE_EVIDENCE_NOT_FOUND")

    async def test_valid_needs_changes_guards_pass(self) -> None:
        assignment = _make_assignment(state="in_review")
        request = _request(assignment, verdict="needs_changes", issues=(_issue(assignment, assignee=None),))
        await SubmitReviewGuards(Mock(spec=ReviewRepository)).validate(_session(request, assignment.reviewer_employee_id), assignment, request)


class TestRerunReviewHandler:
    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_creates_rerun_assignment(self, mock_hash) -> None:
        repo = Mock(spec=ReviewRepository)
        repo.create_rerun_assignment = AsyncMock(return_value=(Mock(), Mock(), Mock()))
        uow = Mock()
        session = AsyncMock()

        async def fake_execute(_ctx, _sha, command):
            result = await command(session)
            return result.response if isinstance(result, CommandResult) else result

        uow.execute = AsyncMock(side_effect=fake_execute)
        handler = RerunReviewHandler(repo, uow)
        request = RerunReview(company_id=uuid.uuid4(), review_id=uuid.uuid4())

        result = await handler.handle("ctx", request)
        assert result == {"status": "queued"}
        repo.create_rerun_assignment.assert_awaited_once_with(session, request.company_id, request.review_id)
