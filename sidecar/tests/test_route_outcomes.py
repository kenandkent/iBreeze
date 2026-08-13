from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from ibreeze.routing.outcomes import local_calibration, project_outcome


def test_outcome_mapping_and_stable_source_id() -> None:
    decision_id = str(uuid4())
    source_id = str(uuid4())
    result = project_outcome(decision_id, "review", source_id, "review_passed", has_blocker=True)
    assert result.score == Decimal("0")
    assert result.label == "review_failed"
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SOURCE_INVALID"):
        project_outcome(decision_id, "review", "random:1", "review_passed")
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SOURCE_INVALID"):
        project_outcome(decision_id, "review", "not-a-uuid", "review_passed")


def test_tool_source_id_is_a_stable_uuid_for_each_call() -> None:
    from ibreeze.routing.outcomes import stable_tool_source_id

    run_id = str(uuid4())
    first = stable_tool_source_id(run_id, 2, "call-a")
    same = stable_tool_source_id(run_id, 2, "call-a")
    different_call = stable_tool_source_id(run_id, 2, "call-b")
    different_turn = stable_tool_source_id(run_id, 3, "call-a")

    assert first == same
    assert first != different_call
    assert first != different_turn
    project_outcome(str(uuid4()), "tool_result", first, "tool_verified")


def test_local_calibration_requires_thirty_samples_and_clamps() -> None:
    assert local_calibration([(1, 0.5)] * 29, catalog_quality_prior=Decimal("0.5")) == Decimal("0")
    samples = [(1, 0.0)] * 30
    assert local_calibration(samples, catalog_quality_prior=Decimal("0.5")) == Decimal("0.20")


def test_local_calibration_uses_purpose_bucket_then_global_fallback() -> None:
    from ibreeze.routing.outcomes import calibration_for_purpose

    global_samples = [(1, 0.5)] * 30
    purpose_samples = [(0, 0.5)] * 30
    assert calibration_for_purpose(
        {"review": purpose_samples, "task_execution": global_samples},
        purpose="review",
        catalog_quality_prior=Decimal("0.5"),
    ) == Decimal("-0.20")
    assert calibration_for_purpose(
        {"verification": global_samples},
        purpose="review",
        catalog_quality_prior=Decimal("0.5"),
    ) == Decimal("0.20")
