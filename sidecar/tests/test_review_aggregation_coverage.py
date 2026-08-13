"""Cover review_aggregation branches the main suite does not reach.

Targets the no-report/no-spec/no-round short-circuits of the private ledger
helpers and the auto-rerun exhaustion path that falls back when the source
reviewer is no longer eligible.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

from ibreeze.application.review_aggregation import (
    _DEFAULT_ROUNDS,
    _DEFAULT_THRESHOLD,
    ReviewAggregationService,
)
from ibreeze.domain.review.repository import ReviewRepository

C1 = "00000000-0000-0000-0000-000000000001"
C2 = "00000000-0000-0000-0000-000000000002"


def _cursor(row, *, rows=()):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=row)
    cursor.fetchall = AsyncMock(return_value=rows)
    return cursor


def _assignment():
    assignment = Mock()
    assignment.id = uuid.uuid4()
    assignment.artifact_id = uuid.uuid4()
    return assignment


def _service(repo=None) -> ReviewAggregationService:
    return ReviewAggregationService(repo or Mock(spec=ReviewRepository))


class TestRecordScore:
    async def test_returns_when_no_report_row(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_cursor(None))
        service = _service()
        await service._record_score(session, company_id=C1, assignment=_assignment())
        session.execute.assert_awaited_once()


class TestSpec:
    async def _session(self, *, artifact_row, spec_row) -> AsyncMock:
        session = AsyncMock()
        calls = {"n": 0}

        async def execute(sql, _params=()):
            calls["n"] += 1
            return _cursor(artifact_row if calls["n"] == 1 else spec_row)

        session.execute = AsyncMock(side_effect=execute)
        return session

    async def test_returns_defaults_when_artifact_missing(self) -> None:
        session = await self._session(artifact_row=None, spec_row=None)
        result = await _service()._spec(session, company_id=C1, artifact_id=C2)
        assert result == (_DEFAULT_ROUNDS, _DEFAULT_THRESHOLD)

    async def test_returns_defaults_when_spec_missing(self) -> None:
        session = await self._session(
            artifact_row={"company_task_id": "t1", "artifact_type": "document"},
            spec_row=None,
        )
        result = await _service()._spec(session, company_id=C1, artifact_id=C2)
        assert result == (_DEFAULT_ROUNDS, _DEFAULT_THRESHOLD)


class TestRoundState:
    async def test_returns_round_one_when_no_assignments(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_cursor(None, rows=[]))
        result = await _service()._round_state(session, company_id=C1, artifact_id=C2)
        assert result == (1, 0)


class TestCreateAutoRerun:
    async def test_returns_none_when_no_submitted_report(self) -> None:
        repo = Mock(spec=ReviewRepository)
        service = _service(repo)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_cursor(None))
        result = await service._create_auto_rerun(session, company_id=C1, artifact_id=C2)
        assert result == (None, None)
        repo.create_rerun_assignment.assert_not_called()

    async def test_exhausts_verdict_when_rerun_ineligible(self) -> None:
        repo = Mock(spec=ReviewRepository)
        repo.create_rerun_assignment = AsyncMock(side_effect=ValueError("REVIEWER_NOT_ELIGIBLE"))
        service = _service(repo)
        session = AsyncMock()
        state = {"n": 0}

        async def execute(sql, _params=()):
            state["n"] += 1
            if state["n"] == 1:
                return _cursor({"id": str(uuid.uuid4())})
            return _cursor(None)

        session.execute = AsyncMock(side_effect=execute)
        result = await service._create_auto_rerun(session, company_id=C1, artifact_id=C2)
        assert result == (None, None)
        assert state["n"] == 2  # report lookup + rerun_exhausted UPDATE
        repo.create_rerun_assignment.assert_awaited_once()
