from __future__ import annotations

import json
import uuid
from unittest.mock import ANY, AsyncMock, Mock, patch
from uuid import UUID

import pytest

from ibreeze.application.review_aggregation import AggregationOutcome
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
from ibreeze.persistence.types import DomainEventRecord, OutboxRecord
from ibreeze.persistence.unit_of_work import CommandResult

_REAL_MOCK = Mock
_DEFAULT_COMPANY_ID = UUID("00000000-0000-0000-0000-000000000099")


def Mock(*args, **kwargs):  # noqa: N802
    """Create request mocks with the required company scope by default."""
    spec = kwargs.get("spec")
    if spec in {
        StartReview,
        SubmitReview,
        StartIssueFix,
        ResolveIssue,
        VerifyIssue,
        CloseIssue,
        RejectIssue,
    }:
        kwargs.setdefault("company_id", _DEFAULT_COMPANY_ID)
    return _REAL_MOCK(*args, **kwargs)


@pytest.fixture
def repo():
    repo = Mock(spec=ReviewRepository)
    repo.lock_assignment = AsyncMock()
    repo.lock_issue = AsyncMock()
    repo.transition = AsyncMock()
    repo.transition_issue = AsyncMock()
    repo.resolve_issue_with_evidence = AsyncMock()
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
        await SubmitReviewGuards(guards_repo).validate(session, assignment, request)

    async def _assert_guards_raises(self, guards_repo, session, assignment, request, expected_msg):
        with pytest.raises(ValueError, match=expected_msg):
            await SubmitReviewGuards(guards_repo).validate(session, assignment, request)

    @staticmethod
    def _session(
        request: SubmitReview,
        reviewer_employee_id: UUID,
        *,
        contributor: bool = False,
    ) -> AsyncMock:
        session = AsyncMock()

        async def execute(sql: str, _params: tuple[object, ...] = ()):
            if "FROM agent_runs" in sql:
                row = {
                    "employee_id": str(reviewer_employee_id),
                    "run_purpose": "review",
                    "status": "succeeded",
                    "company_id": str(request.company_id),
                }
            elif "object_sha256" in sql:
                row = {
                    "object_sha256": request.reviewed_sha256,
                    "is_current": 1,
                    "company_id": str(request.company_id),
                }
            elif "artifact_type" in sql:
                row = {
                    "artifact_type": "review_report",
                    "company_id": str(request.company_id),
                    "created_by_type": "agent",
                    "created_by_run_id": str(request.reviewer_run_id),
                }
            elif "artifact_contributors" in sql:
                row = {"1": 1} if contributor else None
            elif "FROM employees" in sql:
                row = {"1": 1}
            elif "FROM artifacts" in sql:
                row = {"1": 1}
            else:
                row = None
            return _fetchone_cursor(row)

        session.execute = AsyncMock(side_effect=execute)
        return session

    @staticmethod
    def _request(assignment: ReviewAssignment, verdict: str, issues: tuple[ReviewIssueInput, ...], company_id: UUID):
        return SubmitReview(
            company_id=company_id,
            assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(),
            reviewed_artifact_id=assignment.artifact_id,
            reviewed_sha256=assignment.artifact_sha256,
            report_artifact_id=uuid.uuid4(),
            verdict=verdict,
            issues=issues,
            expected_assignment_version=assignment.version,
        )

    @staticmethod
    def _issue(assignment: ReviewAssignment, *, severity: str = "high", category: str = "functional"):
        return ReviewIssueInput(
            client_issue_id=uuid.uuid4(), severity=severity, category=category,
            description="test", expected="ok", actual="bad",
            evidence_refs=(assignment.artifact_id,), suggested_fix="fix",
            assignee_employee_id=None,
        )

    async def test_valid_pass_verdict(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = self._request(assignment, "pass", (), company_id)
        await self._assert_guards_ok(
            guards_repo, self._session(request, assignment.reviewer_employee_id), assignment, request,
        )

    async def test_valid_needs_changes_verdict(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="in_review", version=1)
        request = self._request(assignment, "needs_changes", (self._issue(assignment),), company_id)
        await self._assert_guards_ok(
            guards_repo, self._session(request, assignment.reviewer_employee_id), assignment, request,
        )

    async def test_valid_failed_verdict(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        issue = self._issue(assignment, severity="blocker", category="review_execution")
        request = self._request(assignment, "failed", (issue,), company_id)
        await self._assert_guards_ok(
            guards_repo, self._session(request, assignment.reviewer_employee_id), assignment, request,
        )

    async def test_state_not_assigned_nor_in_review(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="submitted", version=1)
        request = self._request(assignment, "pass", (), company_id)
        await self._assert_guards_raises(guards_repo, AsyncMock(), assignment, request, "STATE_TRANSITION_INVALID")

    async def test_version_mismatch(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=2)
        request = SubmitReview(
            company_id=company_id, assignment_id=assignment.id,
            reviewer_run_id=uuid.uuid4(), reviewed_artifact_id=assignment.artifact_id,
            reviewed_sha256=assignment.artifact_sha256, report_artifact_id=uuid.uuid4(),
            verdict="pass", issues=(), expected_assignment_version=1,
        )
        await self._assert_guards_raises(guards_repo, AsyncMock(), assignment, request, "OPTIMISTIC_LOCK_CONFLICT")

    async def test_self_assignment(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = self._request(assignment, "pass", (), company_id)
        await self._assert_guards_raises(
            guards_repo,
            self._session(request, assignment.reviewer_employee_id, contributor=True),
            assignment,
            request,
            "REVIEW_SELF_ASSIGNMENT",
        )

    async def test_verdict_pass_with_issues(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = self._request(assignment, "pass", (self._issue(assignment),), company_id)
        await self._assert_guards_raises(
            guards_repo, self._session(request, assignment.reviewer_employee_id), assignment, request,
            "VERDICT_PASS_WITH_ISSUES",
        )

    async def test_verdict_needs_changes_without_issues(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = self._request(assignment, "needs_changes", (), company_id)
        await self._assert_guards_raises(
            guards_repo, self._session(request, assignment.reviewer_employee_id), assignment, request,
            "VERDICT_NEEDS_CHANGES_WITHOUT_ISSUES",
        )

    async def test_verdict_failed_missing_blocker_review_exec(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        request = self._request(assignment, "failed", (self._issue(assignment),), company_id)
        await self._assert_guards_raises(
            guards_repo, self._session(request, assignment.reviewer_employee_id), assignment, request,
            "VERDICT_FAILED_MISSING_BLOCKER_REVIEW_EXECUTION",
        )

    async def test_verdict_failed_blocker_wrong_category(self, guards_repo, company_id):
        assignment = _make_assignment(company_id=company_id, state="assigned", version=1)
        issue = self._issue(assignment, severity="blocker", category="security")
        request = self._request(assignment, "failed", (issue,), company_id)
        await self._assert_guards_raises(
            guards_repo, self._session(request, assignment.reviewer_employee_id), assignment, request,
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
        repo.lock_assignment.assert_awaited_once_with(ANY, request.assignment_id, request.company_id)
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
    async def test_start_review_has_no_additional_events(self, mock_hash, repo, uow):
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

        # Assignment creation already emits review.assigned.  Starting the
        # review only changes the aggregate state inside this command.
        assert events_captured == []

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

        assert result == {"review_id": str(report.id)}

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
        assert result == {"review_id": str(report.id)}

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
        payload = json.loads(ev.payload_json)
        assert payload["assignment_id"] == str(assignment.id)
        assert payload["verdict"] == "pass"
        assert ev["company_id"] == str(company_id)

        assert len(captured["outbox"]) == 1
        ob = captured["outbox"][0]
        assert ob.topic == "review.submitted"
        assert json.loads(ob.payload_json)["assignment_id"] == str(assignment.id)
        assert json.loads(ob.payload_json)["company_id"] == str(company_id)

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_appends_auto_rerun_event_to_command_result(self, mock_hash, repo, uow, company_id):
        """F1 wiring: when the aggregation produces an auto round+1, the submit
        handler appends its review.assigned event + outbox to the CommandResult
        so the UoW persists them atomically with the report."""
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

        rerun_event = DomainEventRecord(
            event_id=uuid.uuid4(), event_type="review.assigned",
            aggregate_type="review_assignment", aggregate_id=uuid.uuid4(),
            aggregate_version=1, company_id=company_id,
            payload_json='{"assignment_id":"rr"}', trace_id=str(uuid.uuid4()),
        )
        rerun_outbox = OutboxRecord(
            topic="review.assigned",
            payload_json=rerun_event.payload_json,
            domain_event_id=rerun_event.event_id,
        )
        aggregation = AsyncMock()
        aggregation.on_report_submitted.return_value = AggregationOutcome(
            fused=Mock(), rerun_event=rerun_event, rerun_outbox=rerun_outbox,
        )

        handler = SubmitReviewHandler(repo, guards, uow, aggregation=aggregation)
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

        aggregation.on_report_submitted.assert_awaited_once()
        assert [ev["event_type"] for ev in captured["events"]] == ["review.submitted", "review.assigned"]
        assert len(captured["outbox"]) == 2
        assert captured["outbox"][1].topic == "review.assigned"
        assert captured["outbox"][1].payload_json == rerun_event.payload_json
        assert captured["outbox"][1].domain_event_id == rerun_event.event_id

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_no_aggregation_keeps_single_review_submitted_event(self, mock_hash, repo, uow, company_id):
        """Backward compatibility: without an aggregation service the handler
        emits exactly one review.submitted event (no rerun wiring)."""
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

        assert [ev["event_type"] for ev in captured["events"]] == ["review.submitted"]
        assert len(captured["outbox"]) == 1


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

        assert result == {"success": True}
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id, request.company_id)
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
        assert len(captured["outbox"]) == 1
        assert captured["outbox"][0].topic == "review.issue_changed"


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
        repo.resolve_issue_with_evidence.return_value = result_issue

        request = Mock(spec=ResolveIssue, issue_id=issue.id, expected_version=1)
        result = await self._run(uow, repo, request)

        assert result == {"success": True}
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id, request.company_id)
        repo.resolve_issue_with_evidence.assert_awaited_once()

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
        repo.resolve_issue_with_evidence.side_effect = ValueError("STATE_TRANSITION_INVALID")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await self._run(uow, repo, Mock(spec=ResolveIssue, issue_id=issue.id, expected_version=1))

    @patch("ibreeze.application.review_handlers.canonical_hash", return_value="fakehash")
    async def test_returns_command_result_with_events(self, mock_hash, repo, uow):
        issue = _make_issue(state="fixing", version=1)
        repo.lock_issue.return_value = issue
        result_issue = _make_issue(id=issue.id, severity=issue.severity, state="resolved", version=2)
        repo.resolve_issue_with_evidence.return_value = result_issue

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
        assert len(captured["outbox"]) == 1
        assert captured["outbox"][0].topic == "review.issue_changed"


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

        assert result == {"id": str(issue.id), "state": "verified"}
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id, request.company_id)
        repo.transition_issue.assert_awaited_once_with(
            ANY, issue, "verified", verifier_employee_id=request.verifier_employee_id,
        )

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
    async def test_returns_command_result_with_events_and_outbox(self, mock_hash, repo, uow):
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
            captured["events"] = cmd_result.events
            captured["outbox"] = cmd_result.outbox
            return cmd_result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", request)

        assert captured["result_type"] == "CommandResult"
        assert result == {"id": str(issue.id), "state": "verified"}
        assert len(captured["events"]) == 1
        ev = captured["events"][0]
        assert ev["event_type"] == "review.issue_changed"
        assert ev["from_state"] == "resolved"
        assert ev["to_state"] == "verified"
        assert len(captured["outbox"]) == 1


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

        assert result == {"id": str(issue.id), "state": "closed"}
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id, request.company_id)
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
        assert ob.topic == "review.issue_changed"
        ob_payload = json.loads(ob.payload_json)
        assert ob_payload["issue_id"] == str(issue.id)
        assert ob_payload["company_id"] == str(issue.company_id)


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

        assert result == {"id": str(issue.id), "state": "rejected"}
        repo.lock_issue.assert_awaited_once_with(ANY, request.issue_id, request.company_id)
        repo.transition_issue.assert_awaited_once_with(
            ANY, issue, "rejected", rejection_reason=request.rejection_reason,
        )

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
        assert len(captured["outbox"]) == 1
