"""Coverage-focused tests for ``ibreeze.domain.review.repository``.

Targets the uncovered branches of :class:`ReviewRepository`:

- ``create_rerun_assignment`` guards (RESOURCE_NOT_FOUND, REVIEW_STALE_ARTIFACT,
  REVIEW_HASH_MISMATCH, REVIEWER_NOT_AVAILABLE, REVIEWER_CANNOT_BE_CONTRIBUTOR)
- ``lock_issue`` invalid evidence JSON (REVIEW_ISSUE_EVIDENCE_INVALID)
- ``transition_issue`` rejection / verification branches (REJECTION_REASON_REQUIRED,
  VERIFIER_REQUIRED, VERIFIER_NOT_AVAILABLE, VERIFIER_NOT_ALLOWED)
- ``resolve_issue_with_evidence`` (every guard plus the happy path)

The repository talks to the ``session`` only through ``execute``, so a mock
session whose ``execute`` dispatches on SQL text exercises every branch without
a real database.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from ibreeze.domain.review.entities import ReviewAssignment, ReviewIssue
from ibreeze.domain.review.repository import ReviewRepository

_SHA = "a" * 64


@pytest.fixture
def repo() -> ReviewRepository:
    return ReviewRepository()


@pytest.fixture
def company_id() -> UUID:
    return uuid.uuid4()


def _make_cursor(row: object = None, *, rowcount: int = 1) -> AsyncMock:
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=row)
    cursor.rowcount = rowcount
    return cursor


def _make_session(factory) -> AsyncMock:
    session = AsyncMock()

    async def execute(sql, parameters=()):
        return factory(sql)

    session.execute = AsyncMock(side_effect=execute)
    return session


def _rerun_report_row(*, reviewed_sha256: str = _SHA) -> dict:
    return {
        "company_id": str(uuid.uuid4()),
        "artifact_id": str(uuid.uuid4()),
        "reviewer_employee_id": str(uuid.uuid4()),
        "review_round": 1,
        "reviewed_sha256": reviewed_sha256,
    }


def _issue(*, severity: str = "medium", state: str = "fixing", version: int = 1) -> ReviewIssue:
    return ReviewIssue(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        severity=severity,  # type: ignore[arg-type]
        category="functional",
        state=state,
        version=version,
    )


class TestCreateRerunAssignmentGuards:
    """Error branches of create_rerun_assignment."""

    async def test_raises_resource_not_found(self, repo):
        session = _make_session(lambda sql: _make_cursor(row=None))

        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await repo.create_rerun_assignment(
                session, company_id=uuid.uuid4(), review_id=uuid.uuid4()
            )

    async def test_raises_review_stale_artifact(self, repo):
        def factory(sql):
            if "FROM review_reports" in sql:
                return _make_cursor(row=_rerun_report_row())
            return _make_cursor(row=None)  # artifact lookup misses

        with pytest.raises(ValueError, match="REVIEW_STALE_ARTIFACT"):
            await repo.create_rerun_assignment(
                _make_session(factory), company_id=uuid.uuid4(), review_id=uuid.uuid4()
            )

    async def test_raises_review_hash_mismatch(self, repo):
        def factory(sql):
            if "FROM review_reports" in sql:
                return _make_cursor(row=_rerun_report_row())
            if "FROM artifacts" in sql:
                return _make_cursor(row={"object_sha256": "b" * 64, "is_current": 1})
            return _make_cursor()

        with pytest.raises(ValueError, match="REVIEW_HASH_MISMATCH"):
            await repo.create_rerun_assignment(
                _make_session(factory), company_id=uuid.uuid4(), review_id=uuid.uuid4()
            )

    async def test_raises_reviewer_not_available(self, repo):
        def factory(sql):
            if "FROM review_reports" in sql:
                return _make_cursor(row=_rerun_report_row())
            if "FROM artifacts" in sql:
                return _make_cursor(row={"object_sha256": _SHA, "is_current": 1})
            return _make_cursor(row=None)  # employee lookup misses

        with pytest.raises(ValueError, match="REVIEWER_NOT_AVAILABLE"):
            await repo.create_rerun_assignment(
                _make_session(factory), company_id=uuid.uuid4(), review_id=uuid.uuid4()
            )

    async def test_raises_reviewer_cannot_be_contributor(self, repo):
        def factory(sql):
            if "FROM review_reports" in sql:
                return _make_cursor(row=_rerun_report_row())
            if "FROM artifacts" in sql:
                return _make_cursor(row={"object_sha256": _SHA, "is_current": 1})
            if "FROM employees" in sql:
                return _make_cursor(row={"1": 1})
            return _make_cursor(row={"1": 1})  # contributor row found

        with pytest.raises(ValueError, match="REVIEWER_CANNOT_BE_CONTRIBUTOR"):
            await repo.create_rerun_assignment(
                _make_session(factory), company_id=uuid.uuid4(), review_id=uuid.uuid4()
            )

    async def test_returns_rerun_assignment(self, repo):
        """Happy path returns the round+1 assignment plus event/outbox records."""

        def factory(sql):
            if "FROM review_reports" in sql:
                return _make_cursor(row=_rerun_report_row())
            if "FROM artifacts" in sql:
                return _make_cursor(row={"object_sha256": _SHA, "is_current": 1})
            if "FROM employees" in sql:
                return _make_cursor(row={"1": 1})
            return _make_cursor(row=None)  # contributor lookup / INSERTs

        assignment, event, outbox = await repo.create_rerun_assignment(
            _make_session(factory), company_id=uuid.uuid4(), review_id=uuid.uuid4()
        )

        assert isinstance(assignment, ReviewAssignment)
        assert assignment.state == "assigned"
        assert assignment.version == 1
        assert event.event_type == "review.assigned"
        assert outbox.topic == "review.assigned"


class TestLockIssueEvidenceInvalid:
    async def test_raises_when_evidence_json_invalid(self, repo, company_id):
        row = {
            "id": str(uuid.uuid4()),
            "company_id": str(company_id),
            "severity": "medium",
            "category": "functional",
            "status": "open",
            "version": 1,
            "assignee_employee_id": None,
            "verifier_employee_id": None,
            "rejection_reason": None,
            "evidence_refs_json": "{not-json",
        }
        session = _make_session(lambda sql: _make_cursor(row=row))

        with pytest.raises(ValueError, match="REVIEW_ISSUE_EVIDENCE_INVALID"):
            await repo.lock_issue(session, uuid.uuid4(), company_id)

    async def test_parses_valid_evidence_refs(self, repo, company_id):
        ref = str(uuid.uuid4())
        row = {
            "id": str(uuid.uuid4()),
            "company_id": str(company_id),
            "severity": "medium",
            "category": "functional",
            "status": "open",
            "version": 1,
            "assignee_employee_id": None,
            "verifier_employee_id": None,
            "rejection_reason": None,
            "evidence_refs_json": f'["{ref}"]',
        }
        session = _make_session(lambda sql: _make_cursor(row=row))

        result = await repo.lock_issue(session, uuid.uuid4(), company_id)

        assert result.evidence_refs == (ref,)


class TestTransitionIssueRejectionAndVerification:
    async def test_rejection_requires_reason(self, repo, mock_db_session):
        issue = _issue(state="open")

        with pytest.raises(ValueError, match="REJECTION_REASON_REQUIRED"):
            await repo.transition_issue(mock_db_session, issue, "rejected", rejection_reason="  ")

    async def test_rejection_reason_too_long(self, repo, mock_db_session):
        issue = _issue(state="open")

        with pytest.raises(ValueError, match="REJECTION_REASON_REQUIRED"):
            await repo.transition_issue(mock_db_session, issue, "rejected", rejection_reason="x" * 2001)

    async def test_verified_requires_verifier(self, repo, mock_db_session):
        issue = _issue(state="resolved")

        with pytest.raises(ValueError, match="VERIFIER_REQUIRED"):
            await repo.transition_issue(mock_db_session, issue, "verified")

    async def test_verified_verifier_not_available(self, repo):
        issue = _issue(state="resolved")
        session = _make_session(lambda sql: _make_cursor(row=None))

        with pytest.raises(ValueError, match="VERIFIER_NOT_AVAILABLE"):
            await repo.transition_issue(
                session, issue, "verified", verifier_employee_id=uuid.uuid4()
            )

    async def test_verified_with_active_verifier(self, repo):
        company = uuid.uuid4()
        issue = ReviewIssue(
            id=uuid.uuid4(),
            company_id=company,
            severity="medium",
            category="functional",
            state="resolved",
            version=1,
        )

        def factory(sql):
            if "FROM employees" in sql:
                return _make_cursor(row={"1": 1})
            return _make_cursor(rowcount=1)

        session = _make_session(factory)
        verifier = uuid.uuid4()
        result = await repo.transition_issue(
            session, issue, "verified", verifier_employee_id=verifier
        )

        assert result.state == "verified"
        assert result.verifier_employee_id == verifier
        assert result.version == 2
        sql = session.execute.call_args_list[0][0][0]
        assert "status='active'" in sql

    async def test_verifier_not_allowed_for_non_verified_target(self, repo, mock_db_session):
        issue = _issue(state="open")

        with pytest.raises(ValueError, match="VERIFIER_NOT_ALLOWED"):
            await repo.transition_issue(
                mock_db_session, issue, "fixing", verifier_employee_id=uuid.uuid4()
            )


class TestResolveIssueWithEvidence:
    _FIX_RUN_ID = uuid.uuid4()
    _RETEST_RESULT_ID = uuid.uuid4()
    _SUMMARY = "fixed the race condition"

    def _resolve(self, repo, session, issue, expected_version=1):
        return repo.resolve_issue_with_evidence(
            session,
            issue,
            resolution_artifact_sha256=_SHA,
            fix_run_id=self._FIX_RUN_ID,
            retest_result_id=self._RETEST_RESULT_ID,
            resolution_summary=self._SUMMARY,
            expected_version=expected_version,
        )

    async def test_raises_when_not_fixing(self, repo, mock_db_session):
        issue = _issue(state="open")

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._resolve(repo, mock_db_session, issue)

    async def test_raises_version_mismatch(self, repo, mock_db_session):
        issue = _issue(state="fixing", version=3)

        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._resolve(repo, mock_db_session, issue, expected_version=1)

    @pytest.mark.parametrize("sha", ["a" * 63, "g" * 64, "A" * 64])
    async def test_raises_invalid_hash(self, repo, mock_db_session, sha):
        issue = _issue(state="fixing")

        with pytest.raises(ValueError, match="RESOLUTION_ARTIFACT_HASH_INVALID"):
            await repo.resolve_issue_with_evidence(
                mock_db_session,
                issue,
                resolution_artifact_sha256=sha,
                fix_run_id=self._FIX_RUN_ID,
                retest_result_id=self._RETEST_RESULT_ID,
                resolution_summary=self._SUMMARY,
                expected_version=1,
            )

    @pytest.mark.parametrize("summary", ["", "x" * 20_001])
    async def test_raises_invalid_summary(self, repo, mock_db_session, summary):
        issue = _issue(state="fixing")

        with pytest.raises(ValueError, match="RESOLUTION_SUMMARY_INVALID"):
            await repo.resolve_issue_with_evidence(
                mock_db_session,
                issue,
                resolution_artifact_sha256=_SHA,
                fix_run_id=self._FIX_RUN_ID,
                retest_result_id=self._RETEST_RESULT_ID,
                resolution_summary=summary,
                expected_version=1,
            )

    async def test_raises_artifact_not_found(self, repo):
        issue = _issue(state="fixing")
        session = _make_session(lambda sql: _make_cursor(row=None))

        with pytest.raises(ValueError, match="RESOLUTION_ARTIFACT_NOT_FOUND"):
            await self._resolve(repo, session, issue)

    async def test_raises_fix_run_not_complete(self, repo):
        issue = _issue(state="fixing")

        def factory(sql):
            if "object_sha256" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            return _make_cursor(row=None)

        with pytest.raises(ValueError, match="FIX_RUN_NOT_COMPLETE"):
            await self._resolve(repo, _make_session(factory), issue)

    async def test_raises_retest_result_not_found(self, repo):
        issue = _issue(state="fixing")

        def factory(sql):
            if "object_sha256" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            if "FROM agent_runs" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            return _make_cursor(row=None)

        with pytest.raises(ValueError, match="RETEST_RESULT_NOT_FOUND"):
            await self._resolve(repo, _make_session(factory), issue)

    async def test_resolves_issue(self, repo):
        issue = _issue(state="fixing", version=2)

        def factory(sql):
            if "object_sha256" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            if "FROM agent_runs" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            if "artifact_type" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            if sql.startswith("INSERT"):
                return _make_cursor()
            return _make_cursor(rowcount=1)

        result = await self._resolve(repo, _make_session(factory), issue, expected_version=2)

        assert result.state == "resolved"
        assert result.version == 3
        assert result.evidence_refs == issue.evidence_refs

    async def test_raises_update_optimistic_lock_conflict(self, repo):
        issue = _issue(state="fixing", version=1)

        def factory(sql):
            if "object_sha256" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            if "FROM agent_runs" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            if "artifact_type" in sql:
                return _make_cursor(row={"id": str(uuid.uuid4())})
            if sql.startswith("INSERT"):
                return _make_cursor()
            return _make_cursor(rowcount=0)

        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._resolve(repo, _make_session(factory), issue)
