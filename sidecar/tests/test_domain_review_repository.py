from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, PropertyMock
from uuid import UUID

import pytest

from ibreeze.domain.review.entities import ReviewAssignment, ReviewIssue, ReviewReport
from ibreeze.domain.review.repository import ReviewRepository


@pytest.fixture
def repo() -> ReviewRepository:
    return ReviewRepository()


@pytest.fixture
def assignment_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def company_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def issue_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_assignment_row(assignment_id: UUID, company_id: UUID) -> dict:
    return {
        "id": str(assignment_id),
        "company_id": str(company_id),
        "artifact_id": str(uuid.uuid4()),
        "reviewed_sha256": "a" * 64,
        "reviewer_employee_id": str(uuid.uuid4()),
        "status": "assigned",
        "version": 1,
    }


@pytest.fixture
def sample_issue_row(issue_id: UUID, company_id: UUID) -> dict:
    return {
        "id": str(issue_id),
        "company_id": str(company_id),
        "severity": "medium",
        "category": "functional",
        "status": "open",
        "version": 1,
    }


class TestLockAssignment:
    async def test_returns_assignment(self, repo, mock_db_session, assignment_id, company_id, sample_assignment_row):
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=sample_assignment_row)
        mock_db_session.execute.return_value = mock_cursor

        result = await repo.lock_assignment(mock_db_session, assignment_id)

        assert isinstance(result, ReviewAssignment)
        assert result.id == assignment_id
        assert result.company_id == company_id
        assert result.state == "assigned"
        assert result.version == 1
        mock_db_session.execute.assert_called_once()

    async def test_raises_resource_not_found(self, repo, mock_db_session, assignment_id):
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_db_session.execute.return_value = mock_cursor

        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await repo.lock_assignment(mock_db_session, assignment_id)

    async def test_selects_without_for_update(self, repo, mock_db_session, assignment_id, sample_assignment_row):
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=sample_assignment_row)
        mock_db_session.execute.return_value = mock_cursor

        await repo.lock_assignment(mock_db_session, assignment_id)

        sql = mock_db_session.execute.call_args[0][0]
        assert "FOR UPDATE" not in sql.upper()
        assert "UPDATE" not in sql.upper()


class TestLockIssue:
    async def test_returns_issue(self, repo, mock_db_session, issue_id, company_id, sample_issue_row):
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=sample_issue_row)
        mock_db_session.execute.return_value = mock_cursor

        result = await repo.lock_issue(mock_db_session, issue_id)

        assert isinstance(result, ReviewIssue)
        assert result.id == issue_id
        assert result.company_id == company_id
        assert result.state == "open"
        assert result.version == 1

    async def test_raises_resource_not_found(self, repo, mock_db_session, issue_id):
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_db_session.execute.return_value = mock_cursor

        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await repo.lock_issue(mock_db_session, issue_id)

    async def test_selects_without_for_update(self, repo, mock_db_session, issue_id, sample_issue_row):
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=sample_issue_row)
        mock_db_session.execute.return_value = mock_cursor

        await repo.lock_issue(mock_db_session, issue_id)

        sql = mock_db_session.execute.call_args[0][0]
        assert "FOR UPDATE" not in sql.upper()


class TestTransition:
    async def test_transitions_assignment(self, repo, mock_db_session, assignment_id, company_id):
        assignment = ReviewAssignment(
            id=assignment_id, company_id=company_id,
            artifact_id=uuid.uuid4(), artifact_sha256="a" * 64,
            reviewer_employee_id=uuid.uuid4(), state="assigned", version=1,
        )
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 1
        mock_db_session.execute.return_value = mock_cursor

        result = await repo.transition(mock_db_session, assignment, "in_review")

        assert result.state == "in_review"
        assert result.version == 2
        assert result.id == assignment_id

    async def test_raises_state_transition_invalid(self, repo, mock_db_session, assignment_id, company_id):
        assignment = ReviewAssignment(
            id=assignment_id, company_id=company_id,
            artifact_id=uuid.uuid4(), artifact_sha256="a" * 64,
            reviewer_employee_id=uuid.uuid4(), state="stale", version=1,
        )

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await repo.transition(mock_db_session, assignment, "in_review")

    async def test_raises_optimistic_lock_conflict(self, repo, mock_db_session, assignment_id, company_id):
        assignment = ReviewAssignment(
            id=assignment_id, company_id=company_id,
            artifact_id=uuid.uuid4(), artifact_sha256="a" * 64,
            reviewer_employee_id=uuid.uuid4(), state="assigned", version=1,
        )
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 0
        mock_db_session.execute.return_value = mock_cursor

        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await repo.transition(mock_db_session, assignment, "in_review")

    async def test_updates_with_version_check(self, repo, mock_db_session, assignment_id, company_id):
        assignment = ReviewAssignment(
            id=assignment_id, company_id=company_id,
            artifact_id=uuid.uuid4(), artifact_sha256="a" * 64,
            reviewer_employee_id=uuid.uuid4(), state="assigned", version=5,
        )
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 1
        mock_db_session.execute.return_value = mock_cursor

        await repo.transition(mock_db_session, assignment, "in_review")

        sql, params = mock_db_session.execute.call_args[0]
        assert "version=?" in sql
        assert 5 in params


class TestTransitionIssue:
    async def test_transitions_issue(self, repo, mock_db_session, issue_id, company_id):
        issue = ReviewIssue(
            id=issue_id, company_id=company_id,
            severity="medium", category="functional", state="open", version=1,
        )
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 1
        mock_db_session.execute.return_value = mock_cursor

        result = await repo.transition_issue(mock_db_session, issue, "fixing")

        assert result.state == "fixing"
        assert result.version == 2

    async def test_raises_blocker_high_cannot_be_rejected(self, repo, mock_db_session, issue_id, company_id):
        for severity in ("blocker", "high"):
            issue = ReviewIssue(
                id=issue_id, company_id=company_id,
                severity=severity, category="functional", state="open", version=1,
            )
            with pytest.raises(ValueError, match="BLOCKER_HIGH_CANNOT_BE_REJECTED"):
                await repo.transition_issue(mock_db_session, issue, "rejected")

    async def test_allows_medium_low_to_be_rejected(self, repo, mock_db_session, issue_id, company_id):
        for severity in ("medium", "low"):
            issue = ReviewIssue(
                id=issue_id, company_id=company_id,
                severity=severity, category="functional", state="open", version=1,
            )
            mock_cursor = AsyncMock()
            mock_cursor.rowcount = 1
            mock_db_session.execute.return_value = mock_cursor

            result = await repo.transition_issue(mock_db_session, issue, "rejected")
            assert result.state == "rejected"

    async def test_raises_state_transition_invalid(self, repo, mock_db_session, issue_id, company_id):
        issue = ReviewIssue(
            id=issue_id, company_id=company_id,
            severity="medium", category="functional", state="closed", version=1,
        )
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await repo.transition_issue(mock_db_session, issue, "open")

    async def test_raises_optimistic_lock_conflict(self, repo, mock_db_session, issue_id, company_id):
        issue = ReviewIssue(
            id=issue_id, company_id=company_id,
            severity="medium", category="functional", state="open", version=1,
        )
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 0
        mock_db_session.execute.return_value = mock_cursor

        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await repo.transition_issue(mock_db_session, issue, "fixing")


class TestCreateReport:
    async def test_inserts_and_returns_report(self, repo, mock_db_session, company_id, assignment_id):
        reviewer_run_id = uuid.uuid4()
        reviewed_artifact_id = uuid.uuid4()
        report_artifact_id = uuid.uuid4()

        result = await repo.create_report(
            mock_db_session, company_id, assignment_id,
            reviewer_run_id, reviewed_artifact_id,
            "a" * 64, "pass", report_artifact_id,
        )

        assert isinstance(result, ReviewReport)
        assert result.company_id == company_id
        assert result.assignment_id == assignment_id
        assert result.verdict == "pass"
        assert result.version == 1
        mock_db_session.execute.assert_called_once()
        sql = mock_db_session.execute.call_args[0][0]
        assert "INSERT INTO review_reports" in sql

    async def test_allows_needs_changes_and_failed_verdicts(self, repo, mock_db_session, company_id, assignment_id):
        for verdict in ("needs_changes", "failed"):
            result = await repo.create_report(
                mock_db_session, company_id, assignment_id,
                uuid.uuid4(), uuid.uuid4(), "a" * 64, verdict, uuid.uuid4(),
            )
            assert result.verdict == verdict


class TestCreateIssues:
    async def test_inserts_multiple_issues(self, repo, mock_db_session, company_id):
        report_id = uuid.uuid4()
        issues_data = [
            {"severity": "blocker", "category": "security", "description": "x"},
            {"severity": "low", "category": "style", "description": "y"},
        ]

        results = await repo.create_issues(mock_db_session, company_id, report_id, issues_data)

        assert len(results) == 2
        assert all(isinstance(r, ReviewIssue) for r in results)
        assert results[0].state == "open"
        assert results[0].version == 1
        assert results[1].state == "open"
        assert mock_db_session.execute.call_count == 2

    async def test_sets_assignee_when_provided(self, repo, mock_db_session, company_id):
        report_id = uuid.uuid4()
        assignee_id = uuid.uuid4()
        issues_data = [
            {"severity": "medium", "category": "functional", "description": "z", "assignee_employee_id": assignee_id},
        ]

        await repo.create_issues(mock_db_session, company_id, report_id, issues_data)

        _, params = mock_db_session.execute.call_args[0]
        assert str(assignee_id) in params or assignee_id in params

    async def test_sets_assignee_none_when_not_provided(self, repo, mock_db_session, company_id):
        report_id = uuid.uuid4()
        issues_data = [
            {"severity": "medium", "category": "functional", "description": "z"},
        ]

        await repo.create_issues(mock_db_session, company_id, report_id, issues_data)

        _, params = mock_db_session.execute.call_args[0]
        assert params[11] is None

    async def test_adds_evidence_json(self, repo, mock_db_session, company_id):
        report_id = uuid.uuid4()
        ref_id = uuid.uuid4()
        issues_data = [
            {"severity": "low", "category": "documentation", "description": "w", "evidence_refs": [ref_id]},
        ]

        await repo.create_issues(mock_db_session, company_id, report_id, issues_data)

        _, params = mock_db_session.execute.call_args[0]
        assert str(ref_id) in params[9]


class TestStaleAssignmentsForHash:
    async def test_returns_matching_assignments(self, repo, mock_db_session, company_id, sample_assignment_row):
        rows = [
            {**sample_assignment_row, "id": str(uuid.uuid4())},
            {**sample_assignment_row, "id": str(uuid.uuid4())},
        ]
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=rows)
        mock_db_session.execute.return_value = mock_cursor

        results = await repo.stale_assignments_for_hash(mock_db_session, "a" * 64)

        assert len(results) == 2
        assert all(isinstance(r, ReviewAssignment) for r in results)

    async def test_excludes_stale_and_cancelled(self, repo, mock_db_session):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_db_session.execute.return_value = mock_cursor

        await repo.stale_assignments_for_hash(mock_db_session, "a" * 64)

        sql = mock_db_session.execute.call_args[0][0]
        assert "NOT IN ('stale','cancelled')" in sql

    async def test_returns_empty_list_when_none_found(self, repo, mock_db_session):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_db_session.execute.return_value = mock_cursor

        results = await repo.stale_assignments_for_hash(mock_db_session, "b" * 64)

        assert results == []
