from __future__ import annotations

import uuid
from unittest.mock import ANY, AsyncMock, Mock, patch
from uuid import UUID

import pytest

from ibreeze.application.review_handlers import (
    CloseIssueHandler,
    RejectIssueHandler,
    ResolveIssueHandler,
    StartIssueFixHandler,
    StartReviewHandler,
    SubmitReviewGuards,
    SubmitReviewHandler,
    VerifyIssueHandler,
)
from ibreeze.domain.review.commands import (
    CloseIssue,
    RejectIssue,
    ResolveIssue,
    ReviewIssueInput,
    StartIssueFix,
    StartReview,
    SubmitReview,
    VerifyIssue,
)
from ibreeze.domain.review.entities import ReviewAssignment, ReviewIssue, ReviewReport
from ibreeze.domain.review.repository import ReviewRepository
from ibreeze.persistence.unit_of_work import CommandResult


@pytest.fixture
def repo():
    repo = Mock(spec=ReviewRepository)
    repo.lock_assignment = AsyncMock()
    repo.lock_issue = AsyncMock()
    repo.transition = AsyncMock()
    repo.transition_issue = AsyncMock()
    repo.create_report = AsyncMock()
    repo.create_issues = AsyncMock()
    return repo


@pytest.fixture
def uow():
    uow = Mock()
    uow.execute = AsyncMock()
    return uow


@pytest.fixture
def company_id() -> UUID:
    return uuid.uuid4()


def _make_session():
    return AsyncMock()


def _fetchone_cursor(row):
    c = AsyncMock()
    c.fetchone = AsyncMock(return_value=row)
    return c


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


def _make_issue(**overrides) -> ReviewIssue:
    return ReviewIssue(
        id=overrides.get("id", uuid.uuid4()),
        company_id=overrides.get("company_id", uuid.uuid4()),
        severity=overrides.get("severity", "medium"),
        category=overrides.get("category", "functional"),
        state=overrides.get("state", "open"),
        version=overrides.get("version", 1),
    )


def _make_report(**overrides) -> ReviewReport:
    return ReviewReport(
        id=overrides.get("id", uuid.uuid4()),
        company_id=overrides.get("company_id", uuid.uuid4()),
        assignment_id=overrides.get("assignment_id", uuid.uuid4()),
        reviewer_run_id=overrides.get("reviewer_run_id", uuid.uuid4()),
        reviewed_artifact_id=overrides.get("reviewed_artifact_id", uuid.uuid4()),
        reviewed_sha256=overrides.get("reviewed_sha256", "a" * 64),
        verdict=overrides.get("verdict", "pass"),
        version=overrides.get("version", 1),
    )


async def _run_command(uow: Mock, context: object, sha: str, command) -> object:
    """Install a side_effect on uow.execute that actually runs the inner command."""
    session = _make_session()

    async def fake_execute(ctx, s, cmd):
        result = await cmd(session)
        if isinstance(result, CommandResult):
            return result.response
        return result

    uow.execute = AsyncMock(side_effect=fake_execute)
    return await uow.execute(context, sha, command)


# ─── SubmitReviewGuards ───────────────────────────────────────────────────────


class TestSubmitReviewGuards:

    @pytest.fixture
    def guards_repo(self):
        return Mock(spec=ReviewRepository)

    async def _assert_guards_ok(self, guards_repo, session, assignment, request):
        guards = SubmitReviewGuards(guards_repo)
        await guards.validate(session, assignment, request)

    async def _assert_guards_raises(self, guards_repo, session, assignment, request, expected_msg):
        guards = SubmitReviewGuards(guards_repo)
        with pytest.raises(ValueError, match=expected_msg):
            await guards.validate(session, assignment, request)

    async def test_valid_pass_verdict(self, guards_repo, company_id):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = Mock(
            spec=SubmitReview,
            company_id=company_id,
            assignment_id=assignment.id,
            artifact_id=uuid.uuid4(),
            reviewer_employee_id=uuid.uuid4(),
            expected_assignment_version=1,
            verdict="pass",
            issues=(),
        )
        await self._assert_guards_ok(guards_repo, session, assignment, request)

    async def test_valid_needs_changes_verdict(self, guards_repo, company_id):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        assignment = _make_assignment(company_id=company_id, state="in_review", version=1)
        issue_input = Mock(
            spec=ReviewIssueInput,
            severity="high",
            category="functional",
            description="test",
            expected="ok",
            actual="bad",
            evidence_refs=(),
            suggested_fix="fix it",
            assignee_employee_id=None,
        )
        request = Mock(
            spec=SubmitReview,
            company_id=company_id,
            assignment_id=assignment.id,
            artifact_id=uuid.uuid4(),
            reviewer_employee_id=uuid.uuid4(),
            expected_assignment_version=1,
            verdict="needs_changes",
            issues=(issue_input,),
        )
        await self._assert_guards_ok(guards_repo, session, assignment, request)

    async def test_valid_failed_verdict(self, guards_repo, company_id):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        blocker = Mock(
            spec=ReviewIssueInput,
            severity="blocker",
            category="review_execution",
            description="blocker exec",
            expected="",
            actual="",
            evidence_refs=(),
            suggested_fix="",
            assignee_employee_id=None,
        )
        request = Mock(
            spec=SubmitReview,
            company_id=company_id,
            assignment_id=assignment.id,
            artifact_id=uuid.uuid4(),
            reviewer_employee_id=uuid.uuid4(),
            expected_assignment_version=1,
            verdict="failed",
            issues=(blocker,),
        )
        await self._assert_guards_ok(guards_repo, session, assignment, request)

    async def test_state_not_assigned_nor_in_review(self, guards_repo, company_id):
        session = AsyncMock()
        assignment = _make_assignment(company_id=company_id, state="submitted", version=1)
        request = Mock(
            spec=SubmitReview,
            expected_assignment_version=1,
            verdict="pass",
            issues=(),
        )
        await self._assert_guards_raises(
            guards_repo, session, assignment, request, "STATE_TRANSITION_INVALID",
        )

    async def test_version_mismatch(self, guards_repo, company_id):
        session = AsyncMock()
        assignment = _make_assignment(company_id=company_id, state="assigned", version=2)
        request = Mock(
            spec=SubmitReview,
            expected_assignment_version=1,
            verdict="pass",
            issues=(),
        )
        await self._assert_guards_raises(
            guards_repo, session, assignment, request, "OPTIMISTIC_LOCK_CONFLICT",
        )

    async def test_self_assignment(self, guards_repo, company_id):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor({"1": 1}))
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = Mock(
            spec=SubmitReview,
            assignment_id=assignment.id,
            expected_assignment_version=1,
            verdict="pass",
            issues=(),
        )
        await self._assert_guards_raises(
            guards_repo, session, assignment, request, "REVIEW_SELF_ASSIGNMENT",
        )

    async def test_verdict_pass_with_issues(self, guards_repo, company_id):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = Mock(
            spec=SubmitReview,
            expected_assignment_version=1,
            verdict="pass",
            issues=(Mock(spec=ReviewIssueInput),),
        )
        await self._assert_guards_raises(
            guards_repo, session, assignment, request, "VERDICT_PASS_WITH_ISSUES",
        )

    async def test_verdict_needs_changes_without_issues(self, guards_repo, company_id):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = Mock(
            spec=SubmitReview,
            expected_assignment_version=1,
            verdict="needs_changes",
            issues=(),
        )
        await self._assert_guards_raises(
            guards_repo, session, assignment, request,
            "VERDICT_NEEDS_CHANGES_WITHOUT_ISSUES",
        )

    async def test_verdict_failed_missing_blocker_review_exec(self, guards_repo, company_id):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        non_blocker = Mock(
            spec=ReviewIssueInput,
            severity="high",
            category="functional",
            description="test",
            expected="",
            actual="",
            evidence_refs=(),
            suggested_fix="",
            assignee_employee_id=None,
        )
        request = Mock(
            spec=SubmitReview,
            expected_assignment_version=1,
            verdict="failed",
            issues=(non_blocker,),
        )
        await self._assert_guards_raises(
            guards_repo, session, assignment, request,
            "VERDICT_FAILED_MISSING_BLOCKER_REVIEW_EXECUTION",
        )

    async def test_verdict_failed_blocker_wrong_category(self, guards_repo, company_id):
        """Blocker issue exists but category is not review_execution — should fail."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_fetchone_cursor(None))
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        blocker_wrong_cat = Mock(
            spec=ReviewIssueInput,
            severity="blocker",
            category="security",
            description="test",
            expected="",
            actual="",
            evidence_refs=(),
            suggested_fix="",
            assignee_employee_id=None,
        )
        request = Mock(
            spec=SubmitReview,
            expected_assignment_version=1,
            verdict="failed",
            issues=(blocker_wrong_cat,),
        )
        await self._assert_guards_raises(
            guards_repo, session, assignment, request,
            "VERDICT_FAILED_MISSING_BLOCKER_REVIEW_EXECUTION",
        )


# ─── StartReviewHandler ───────────────────────────────────────────────────────


class TestStartReviewHandler:

    async def _run(self, uow, repo, request):
        """Run the handler's inner command via uow.execute mock."""
        handler = StartReviewHandler(repo, uow)

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            if isinstance(cmd_result, CommandResult):
                return cmd_result.response
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)
        return await handler.handle("ctx", request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_starts_review(self, mock_hash, repo, uow):
        assignment = _make_assignment(state="assigned", version=1)
        result_assignment = _make_assignment(
            id=assignment.id, company_id=assignment.company_id,
            artifact_id=assignment.artifact_id,
            artifact_sha256=assignment.artifact_sha256,
            reviewer_employee_id=assignment.reviewer_employee_id,
            state="in_review", version=2,
        )
        repo.lock_assignment.return_value = assignment
        repo.transition.return_value = result_assignment

        request = Mock(spec=StartReview, assignment_id=assignment.id, expected_version=1)

        result = await self._run(uow, repo, request)

        assert result["id"] == str(assignment.id)
        assert result["status"] == "in_review"
        repo.lock_assignment.assert_awaited_once_with(ANY, request.assignment_id)
        repo.transition.assert_awaited_once_with(ANY, assignment, "in_review")

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, repo, uow):
        repo.lock_assignment.side_effect = ValueError("RESOURCE_NOT_FOUND")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await self._run(uow, repo, Mock(spec=StartReview, assignment_id=uuid.uuid4(), expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_optimistic_lock_conflict(self, mock_hash, repo, uow):
        assignment = _make_assignment(state="assigned", version=2)
        repo.lock_assignment.return_value = assignment
        request = Mock(spec=StartReview, assignment_id=assignment.id, expected_version=1)
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._run(uow, repo, request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_state_transition_invalid(self, mock_hash, repo, uow):
        assignment = _make_assignment(state="assigned", version=1)
        repo.lock_assignment.return_value = assignment
        repo.transition.side_effect = ValueError("STATE_TRANSITION_INVALID")
        request = Mock(spec=StartReview, assignment_id=assignment.id, expected_version=1)
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._run(uow, repo, request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_command_result_with_events(self, mock_hash, repo, uow):
        assignment = _make_assignment(state="assigned", version=1)
        result_assignment = _make_assignment(
            id=assignment.id, company_id=assignment.company_id,
            artifact_id=assignment.artifact_id,
            artifact_sha256=assignment.artifact_sha256,
            reviewer_employee_id=assignment.reviewer_employee_id,
            state="in_review", version=2,
        )
        repo.lock_assignment.return_value = assignment
        repo.transition.return_value = result_assignment

        handler = StartReviewHandler(repo, uow)
        request = Mock(spec=StartReview, assignment_id=assignment.id, expected_version=1)

        events_captured = []

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            events_captured.extend(cmd_result.events)
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        await handler.handle("ctx", request)

        assert len(events_captured) == 1
        assert events_captured[0]["event_type"] == "review.assigned"
        assert events_captured[0]["aggregate_id"] == str(assignment.id)
        assert events_captured[0]["from_state"] == "assigned"
        assert events_captured[0]["to_state"] == "in_review"

# ─── SubmitReviewHandler ──────────────────────────────────────────────────────


class TestSubmitReviewHandler:

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_submits_review_with_issues(self, mock_hash, repo, uow, company_id):
        assignment = _make_assignment(state="in_review", version=1)
        repo.lock_assignment.return_value = assignment

        guards = AsyncMock(spec=SubmitReviewGuards)
        guards.validate = AsyncMock()

        report = _make_report(company_id=company_id, assignment_id=assignment.id, verdict="needs_changes")
        repo.create_report.return_value = report

        issue1 = _make_issue(id=uuid.uuid4(), company_id=company_id, severity="high", state="open", version=1)
        issue2 = _make_issue(id=uuid.uuid4(), company_id=company_id, severity="low", state="open", version=1)
        repo.create_issues.return_value = (issue1, issue2)

        result_assignment = _make_assignment(
            id=assignment.id, company_id=assignment.company_id,
            artifact_id=assignment.artifact_id,
            artifact_sha256=assignment.artifact_sha256,
            reviewer_employee_id=assignment.reviewer_employee_id,
            state="submitted", version=2,
        )
        repo.transition.return_value = result_assignment

        handler = SubmitReviewHandler(repo, guards, uow)
        issue_inputs = (
            Mock(
                spec=ReviewIssueInput,
                client_issue_id=uuid.uuid4(), severity="high", category="functional",
                description="desc", expected="exp", actual="act",
                evidence_refs=(uuid.uuid4(),), suggested_fix="fix",
                assignee_employee_id=uuid.uuid4(),
            ),
            Mock(
                spec=ReviewIssueInput,
                client_issue_id=uuid.uuid4(), severity="low", category="style",
                description="desc2", expected="exp2", actual="act2",
                evidence_refs=(), suggested_fix="fix2",
                assignee_employee_id=None,
            ),
        )
        request = Mock(
            spec=SubmitReview,
            company_id=company_id,
            assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(),
            reviewed_artifact_id=uuid.uuid4(),
            reviewed_sha256="a" * 64,
            report_artifact_id=uuid.uuid4(),
            verdict="needs_changes",
            issues=issue_inputs,
            expected_assignment_version=1,
        )

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", request)

        assert result["assignment"]["id"] == str(assignment.id)
        assert result["assignment"]["state"] == "submitted"
        assert result["assignment"]["version"] == 2
        assert result["report"]["id"] == str(report.id)
        assert result["report"]["verdict"] == "needs_changes"
        assert len(result["issues"]) == 2
        assert result["issues"][0]["id"] == str(issue1.id)
        assert result["issues"][1]["id"] == str(issue2.id)

        guards.validate.assert_awaited_once()
        repo.create_report.assert_awaited_once()
        repo.create_issues.assert_awaited_once()
        repo.transition.assert_awaited_once_with(ANY, assignment, "submitted")

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_submits_review_pass_no_issues(self, mock_hash, repo, uow, company_id):
        assignment = _make_assignment(state="in_review", version=1)
        repo.lock_assignment.return_value = assignment

        guards = AsyncMock(spec=SubmitReviewGuards)
        guards.validate = AsyncMock()

        report = _make_report(company_id=company_id, assignment_id=assignment.id, verdict="pass")
        repo.create_report.return_value = report
        repo.create_issues.return_value = ()

        result_assignment = _make_assignment(
            id=assignment.id, company_id=assignment.company_id,
            artifact_id=assignment.artifact_id,
            state="submitted", version=2,
        )
        repo.transition.return_value = result_assignment

        handler = SubmitReviewHandler(repo, guards, uow)
        request = Mock(
            spec=SubmitReview,
            company_id=company_id, assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(), reviewed_artifact_id=uuid.uuid4(),
            reviewed_sha256="a" * 64, report_artifact_id=uuid.uuid4(),
            verdict="pass", issues=(),
            expected_assignment_version=1,
        )

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", request)
        assert result["assignment"]["state"] == "submitted"
        assert result["report"]["verdict"] == "pass"
        assert result["issues"] == []

    async def _run(self, uow, repo, guards, request):
        handler = SubmitReviewHandler(repo, guards, uow)

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            if isinstance(cmd_result, CommandResult):
                return cmd_result.response
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)
        return await handler.handle("ctx", request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, repo, uow):
        repo.lock_assignment.side_effect = ValueError("RESOURCE_NOT_FOUND")
        guards = AsyncMock(spec=SubmitReviewGuards)
        request = Mock(spec=SubmitReview, assignment_id=uuid.uuid4(), expected_assignment_version=1)
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await self._run(uow, repo, guards, request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_guard_error(self, mock_hash, repo, uow, company_id):
        assignment = _make_assignment(state="in_review", version=1)
        repo.lock_assignment.return_value = assignment
        guards = AsyncMock(spec=SubmitReviewGuards)
        guards.validate = AsyncMock(side_effect=ValueError("REVIEW_SELF_ASSIGNMENT"))
        request = Mock(
            spec=SubmitReview,
            company_id=company_id, assignment_id=assignment.id,
            expected_assignment_version=1, verdict="pass", issues=(),
        )
        with pytest.raises(ValueError, match="REVIEW_SELF_ASSIGNMENT"):
            await self._run(uow, repo, guards, request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_command_result_with_events_and_outbox(self, mock_hash, repo, uow, company_id):
        assignment = _make_assignment(state="in_review", version=1)
        repo.lock_assignment.return_value = assignment

        guards = AsyncMock(spec=SubmitReviewGuards)
        guards.validate = AsyncMock()

        report = _make_report(company_id=company_id, assignment_id=assignment.id, verdict="pass")
        repo.create_report.return_value = report
        repo.create_issues.return_value = ()
        result_assignment = _make_assignment(
            id=assignment.id, company_id=company_id,
            state="submitted", version=2,
        )
        repo.transition.return_value = result_assignment

        handler = SubmitReviewHandler(repo, guards, uow)
        request = Mock(
            spec=SubmitReview,
            company_id=company_id, assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(), reviewed_artifact_id=uuid.uuid4(),
            reviewed_sha256="a" * 64, report_artifact_id=uuid.uuid4(),
            verdict="pass", issues=(),
            expected_assignment_version=1,
        )

        captured = {}

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            captured["events"] = cmd_result.events
            captured["outbox"] = cmd_result.outbox
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        await handler.handle("ctx", request)

        assert len(captured["events"]) == 1
        ev = captured["events"][0]
        assert ev["event_type"] == "review.submitted"
        assert ev["aggregate_id"] == str(assignment.id)
        assert ev["aggregate_type"] == "review_assignment"
        assert ev["from_state"] == "in_review"
        assert ev["to_state"] == "submitted"
        assert ev["company_id"] == str(company_id)

        assert len(captured["outbox"]) == 1
        ob = captured["outbox"][0]
        assert ob["command_type"] == "EvaluateEmployeeAcceptance"
        assert ob["payload"]["assignment_id"] == str(assignment.id)
        assert ob["payload"]["company_id"] == str(company_id)


# ─── StartIssueFixHandler ─────────────────────────────────────────────────────


class TestStartIssueFixHandler:

    async def _run(self, uow, repo, request):
        handler = StartIssueFixHandler(repo, uow)

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            if isinstance(cmd_result, CommandResult):
                return cmd_result.response
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)
        return await handler.handle("ctx", request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_starts_fix(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, company_id=issue.company_id,
            severity=issue.severity, category=issue.category,
            state="fixing", version=2,
        )
        repo.transition_issue.return_value = result_issue

        request = Mock(spec=StartIssueFix, issue_id=issue.id, expected_version=1)

        result = await self._run(uow, repo, request)

        assert result["id"] == str(issue.id)
        assert result["state"] == "fixing"
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id)
        repo.transition_issue.assert_awaited_once_with(ANY, issue, "fixing")

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, repo, uow):
        repo.lock_issue.side_effect = ValueError("RESOURCE_NOT_FOUND")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await self._run(uow, repo, Mock(spec=StartIssueFix, issue_id=uuid.uuid4(), expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_optimistic_lock_conflict(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=2)
        repo.lock_issue.return_value = issue
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._run(uow, repo, Mock(spec=StartIssueFix, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_state_transition_invalid(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=1)
        repo.lock_issue.return_value = issue
        repo.transition_issue.side_effect = ValueError("STATE_TRANSITION_INVALID")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._run(uow, repo, Mock(spec=StartIssueFix, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_command_result_with_events(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, severity=issue.severity,
            state="fixing", version=2,
        )
        repo.transition_issue.return_value = result_issue

        handler = StartIssueFixHandler(repo, uow)
        request = Mock(spec=StartIssueFix, issue_id=issue.id, expected_version=1)

        captured = {}

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            captured["events"] = cmd_result.events
            captured["outbox"] = cmd_result.outbox
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        await handler.handle("ctx", request)

        assert len(captured["events"]) == 1
        ev = captured["events"][0]
        assert ev["event_type"] == "review.issue_changed"
        assert ev["issue_id"] == str(issue.id)
        assert ev["from_state"] == "open"
        assert ev["to_state"] == "fixing"
        assert captured["outbox"] == ()


# ─── ResolveIssueHandler ──────────────────────────────────────────────────────


class TestResolveIssueHandler:

    async def _run(self, uow, repo, request):
        handler = ResolveIssueHandler(repo, uow)

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            if isinstance(cmd_result, CommandResult):
                return cmd_result.response
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)
        return await handler.handle("ctx", request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_resolves_issue(self, mock_hash, repo, uow):
        issue = _make_issue(state="fixing", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, severity=issue.severity,
            state="resolved", version=2,
        )
        repo.transition_issue.return_value = result_issue

        request = Mock(spec=ResolveIssue, issue_id=issue.id, expected_version=1)
        result = await self._run(uow, repo, request)

        assert result["id"] == str(issue.id)
        assert result["state"] == "resolved"
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id)
        repo.transition_issue.assert_awaited_once_with(ANY, issue, "resolved")

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, repo, uow):
        repo.lock_issue.side_effect = ValueError("RESOURCE_NOT_FOUND")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await self._run(uow, repo, Mock(spec=ResolveIssue, issue_id=uuid.uuid4(), expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_optimistic_lock_conflict(self, mock_hash, repo, uow):
        issue = _make_issue(state="fixing", version=2)
        repo.lock_issue.return_value = issue
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._run(uow, repo, Mock(spec=ResolveIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_state_transition_invalid(self, mock_hash, repo, uow):
        issue = _make_issue(state="fixing", version=1)
        repo.lock_issue.return_value = issue
        repo.transition_issue.side_effect = ValueError("STATE_TRANSITION_INVALID")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._run(uow, repo, Mock(spec=ResolveIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_command_result_with_events(self, mock_hash, repo, uow):
        issue = _make_issue(state="fixing", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(id=issue.id, severity=issue.severity, state="resolved", version=2)
        repo.transition_issue.return_value = result_issue

        handler = ResolveIssueHandler(repo, uow)
        request = Mock(spec=ResolveIssue, issue_id=issue.id, expected_version=1)

        captured = {}

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            captured["events"] = cmd_result.events
            captured["outbox"] = cmd_result.outbox
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        await handler.handle("ctx", request)

        assert len(captured["events"]) == 1
        ev = captured["events"][0]
        assert ev["event_type"] == "review.issue_changed"
        assert ev["from_state"] == "fixing"
        assert ev["to_state"] == "resolved"
        assert captured["outbox"] == ()


# ─── VerifyIssueHandler ───────────────────────────────────────────────────────


class TestVerifyIssueHandler:

    async def _run(self, uow, repo, request):
        handler = VerifyIssueHandler(repo, uow)

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            if isinstance(cmd_result, CommandResult):
                return cmd_result.response
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)
        return await handler.handle("ctx", request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_verifies_issue(self, mock_hash, repo, uow):
        issue = _make_issue(state="resolved", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, company_id=issue.company_id,
            severity=issue.severity, category=issue.category,
            state="verified", version=2,
        )
        repo.transition_issue.return_value = result_issue

        request = Mock(spec=VerifyIssue, issue_id=issue.id, expected_version=1)
        result = await self._run(uow, repo, request)

        assert result["response"]["id"] == str(issue.id)
        assert result["response"]["state"] == "verified"
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id)
        repo.transition_issue.assert_awaited_once_with(ANY, issue, "verified")

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, repo, uow):
        repo.lock_issue.side_effect = ValueError("RESOURCE_NOT_FOUND")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await self._run(uow, repo, Mock(spec=VerifyIssue, issue_id=uuid.uuid4(), expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_optimistic_lock_conflict(self, mock_hash, repo, uow):
        issue = _make_issue(state="resolved", version=2)
        repo.lock_issue.return_value = issue
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._run(uow, repo, Mock(spec=VerifyIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_state_transition_invalid(self, mock_hash, repo, uow):
        issue = _make_issue(state="resolved", version=1)
        repo.lock_issue.return_value = issue
        repo.transition_issue.side_effect = ValueError("STATE_TRANSITION_INVALID")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._run(uow, repo, Mock(spec=VerifyIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_dict_with_events_and_outbox(self, mock_hash, repo, uow):
        issue = _make_issue(state="resolved", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, company_id=issue.company_id,
            severity=issue.severity, state="verified", version=2,
        )
        repo.transition_issue.return_value = result_issue

        handler = VerifyIssueHandler(repo, uow)
        request = Mock(spec=VerifyIssue, issue_id=issue.id, expected_version=1)

        captured = {}

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            captured["result_type"] = type(cmd_result).__name__
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", request)

        assert captured["result_type"] == "dict"
        assert len(result["events"]) == 1
        ev = result["events"][0]
        assert ev["event_type"] == "review.issue_changed"
        assert ev["from_state"] == "resolved"
        assert ev["to_state"] == "verified"
        assert result["outbox"] == ()


# ─── CloseIssueHandler ────────────────────────────────────────────────────────


class TestCloseIssueHandler:

    async def _run(self, uow, repo, request):
        handler = CloseIssueHandler(repo, uow)

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            if isinstance(cmd_result, CommandResult):
                return cmd_result.response
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)
        return await handler.handle("ctx", request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_closes_issue(self, mock_hash, repo, uow):
        issue = _make_issue(state="verified", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, company_id=issue.company_id,
            severity=issue.severity, category=issue.category,
            state="closed", version=2,
        )
        repo.transition_issue.return_value = result_issue

        request = Mock(spec=CloseIssue, issue_id=issue.id, expected_version=1)
        result = await self._run(uow, repo, request)

        assert result["id"] == str(issue.id)
        assert result["state"] == "closed"
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id)
        repo.transition_issue.assert_awaited_once_with(ANY, issue, "closed")

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, repo, uow):
        repo.lock_issue.side_effect = ValueError("RESOURCE_NOT_FOUND")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await self._run(uow, repo, Mock(spec=CloseIssue, issue_id=uuid.uuid4(), expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_optimistic_lock_conflict(self, mock_hash, repo, uow):
        issue = _make_issue(state="verified", version=2)
        repo.lock_issue.return_value = issue
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._run(uow, repo, Mock(spec=CloseIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_state_transition_invalid(self, mock_hash, repo, uow):
        issue = _make_issue(state="verified", version=1)
        repo.lock_issue.return_value = issue
        repo.transition_issue.side_effect = ValueError("STATE_TRANSITION_INVALID")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._run(uow, repo, Mock(spec=CloseIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_command_result_with_events_and_outbox(self, mock_hash, repo, uow):
        issue = _make_issue(state="verified", company_id=uuid.uuid4(), version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, company_id=issue.company_id,
            severity=issue.severity, state="closed", version=2,
        )
        repo.transition_issue.return_value = result_issue

        handler = CloseIssueHandler(repo, uow)
        request = Mock(spec=CloseIssue, issue_id=issue.id, expected_version=1)

        captured = {}

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            captured["events"] = cmd_result.events
            captured["outbox"] = cmd_result.outbox
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        await handler.handle("ctx", request)

        assert len(captured["events"]) == 1
        ev = captured["events"][0]
        assert ev["event_type"] == "review.issue_changed"
        assert ev["issue_id"] == str(issue.id)
        assert ev["from_state"] == "verified"
        assert ev["to_state"] == "closed"

        assert len(captured["outbox"]) == 1
        ob = captured["outbox"][0]
        assert ob["command_type"] == "EvaluateAffectedTask"
        assert ob["payload"]["issue_id"] == str(issue.id)
        assert ob["payload"]["company_id"] == str(issue.company_id)


# ─── RejectIssueHandler ───────────────────────────────────────────────────────


class TestRejectIssueHandler:

    async def _run(self, uow, repo, request):
        handler = RejectIssueHandler(repo, uow)

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            if isinstance(cmd_result, CommandResult):
                return cmd_result.response
            return cmd_result

        uow.execute = AsyncMock(side_effect=fake_execute)
        return await handler.handle("ctx", request)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_rejects_issue(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(
            id=issue.id, company_id=issue.company_id,
            severity=issue.severity, category=issue.category,
            state="rejected", version=2,
        )
        repo.transition_issue.return_value = result_issue

        request = Mock(spec=RejectIssue, issue_id=issue.id, expected_version=1)
        result = await self._run(uow, repo, request)

        assert result["id"] == str(issue.id)
        assert result["state"] == "rejected"
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id)
        repo.transition_issue.assert_awaited_once_with(ANY, issue, "rejected")

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, repo, uow):
        repo.lock_issue.side_effect = ValueError("RESOURCE_NOT_FOUND")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await self._run(uow, repo, Mock(spec=RejectIssue, issue_id=uuid.uuid4(), expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_optimistic_lock_conflict(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=2)
        repo.lock_issue.return_value = issue
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await self._run(uow, repo, Mock(spec=RejectIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_raises_state_transition_invalid(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=1)
        repo.lock_issue.return_value = issue
        repo.transition_issue.side_effect = ValueError("STATE_TRANSITION_INVALID")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._run(uow, repo, Mock(spec=RejectIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_command_result_with_events(self, mock_hash, repo, uow):
        issue = _make_issue(state="open", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(id=issue.id, severity=issue.severity, state="rejected", version=2)
        repo.transition_issue.return_value = result_issue

        handler = RejectIssueHandler(repo, uow)
        request = Mock(spec=RejectIssue, issue_id=issue.id, expected_version=1)

        captured = {}

        async def fake_execute(context, sha, command):
            session = _make_session()
            cmd_result = await command(session)
            captured["events"] = cmd_result.events
            captured["outbox"] = cmd_result.outbox
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        await handler.handle("ctx", request)

        assert len(captured["events"]) == 1
        ev = captured["events"][0]
        assert ev["event_type"] == "review.issue_changed"
        assert ev["from_state"] == "open"
        assert ev["to_state"] == "rejected"
        assert captured["outbox"] == ()
