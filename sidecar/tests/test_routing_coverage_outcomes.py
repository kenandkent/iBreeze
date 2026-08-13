from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from ibreeze.routing.outcomes import RouteOutcomeProjector, load_local_calibrations, outcome_for, project_outcome, stable_tool_source_id


def test_stable_tool_source_id_rejects_invalid_arguments() -> None:
    run_id = str(uuid4())
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SOURCE_INVALID"):
        stable_tool_source_id(run_id, 0, "call-a")
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SOURCE_INVALID"):
        stable_tool_source_id(run_id, 1, "")
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SOURCE_INVALID"):
        stable_tool_source_id(run_id, 1, "call:with:colon")


def test_outcome_for_unknown_event_raises() -> None:
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_EVENT_INVALID"):
        outcome_for("no_such_event")
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_EVENT_INVALID"):
        project_outcome(str(uuid4()), "review", str(uuid4()), "no_such_event")


def test_project_outcome_accepts_compound_stable_source_ids() -> None:
    decision_id = str(uuid4())
    compound = f"{uuid4()}:2"
    result = project_outcome(decision_id, "tool_result", compound, "tool_verified")
    assert result.score == Decimal("1")
    assert result.label == "tool_verified"
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SOURCE_INVALID"):
        project_outcome(decision_id, "tool_result", "not-a-uuid:2", "tool_verified")
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SOURCE_INVALID"):
        project_outcome(decision_id, "tool_result", f"{uuid4()}:0", "tool_verified")


class _FakeOutcomeRepository:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record_outcome(self, db, **kwargs):
        self.calls.append(kwargs)
        return True


def test_projector_with_explicit_repository_appends_outcome() -> None:
    import asyncio

    repo = _FakeOutcomeRepository()
    projector = RouteOutcomeProjector(repository=repo)
    decision_id = str(uuid4())
    result = asyncio.run(
        projector.append(
            object(),
            route_decision_id=decision_id,
            company_id="company-1",
            outcome_type="review",
            source_id=str(uuid4()),
            event="review_passed",
            has_blocker=True,
        )
    )
    assert result is True
    assert repo.calls[0]["outcome_id"].startswith(f"{decision_id}:review:")


class _ReadPool:
    def __init__(self, rows):
        self._rows = rows

    async def query_all(self, _sql, _params):
        return self._rows


def test_load_local_calibrations_early_returns_without_pool() -> None:
    result = __import__("asyncio").run(
        load_local_calibrations(None, company_id="c", purpose="review", candidate_priors={"cand-1": Decimal("0.5")})
    )
    assert result == {"cand-1": Decimal("0")}


def test_load_local_calibrations_builds_purpose_buckets() -> None:
    import asyncio

    rows = [{"candidate_id": "cand-1", "run_purpose": "review", "score": 1.0}] * 30
    rows.append({"candidate_id": "cand-1", "run_purpose": "review", "score": 0.0})
    rows.append({"candidate_id": "cand-1", "run_purpose": "", "score": 1.0})
    rows.append({"candidate_id": "other", "run_purpose": "review", "score": 1.0})
    result = asyncio.run(
        load_local_calibrations(
            _ReadPool(rows),
            company_id="c",
            purpose="review",
            candidate_priors={"cand-1": Decimal("0.5"), "cand-2": Decimal("0.4")},
        )
    )
    assert "cand-1" in result
    assert result["cand-2"] == Decimal("0")
    assert Decimal("-0.20") <= result["cand-1"] <= Decimal("0.20")
