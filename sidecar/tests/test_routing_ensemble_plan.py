from __future__ import annotations

from ibreeze.routing.context import build_routing_context
from ibreeze.routing.ensemble import default_quorum, select_proposer_candidates, should_ensemble


def _candidate(cid: str, provider: str, *, family: str = "same", quality: float = 0.5, latency: int = 100):
    return {
        "candidate_id": cid,
        "provider_release_id": provider,
        "model_vendor": provider,
        "model_family": family,
        "architecture_class": "dense",
        "quality_prior": quality,
        "latency_prior_ms": latency,
    }


def test_default_quorum_and_deterministic_roles() -> None:
    assert [default_quorum(count) for count in (2, 3, 4)] == [2, 2, 3]
    lineup = select_proposer_candidates(
        [(0.9, _candidate("a", "p1")), (0.8, _candidate("b", "p2", family="other")), (0.95, _candidate("c", "p3", quality=0.95))],
        max_proposers=3,
        required_tier="C3",
    )
    assert [role for _candidate_item, role in lineup] == ["anchor", "orthogonal_reviewer", "strong_critic"]
    assert [item["candidate_id"] for item, _role in lineup] == ["c", "b", "a"]


def test_ensemble_trigger_and_context_upper_bound() -> None:
    context = build_routing_context(run_id="r", turn_index=1, messages=({"role": "user", "content": "repair"},), context_window_tokens=1000, run_purpose="repair")
    assert should_ensemble(
        context,
        confidence=0.5,
        proposer_count=2,
        aggregator_available=True,
        estimated_input_tokens=10,
        aggregator_context_window=100000,
        proposer_provider_count=2,
        required_tier="C3",
    )
    assert not should_ensemble(
        context,
        confidence=0.5,
        proposer_count=2,
        aggregator_available=True,
        estimated_input_tokens=100,
        aggregator_context_window=100,
        proposer_provider_count=2,
        required_tier="C3",
    )


def test_repair_and_merge_purpose_do_not_bypass_trigger_thresholds() -> None:
    for purpose in ("repair", "merge"):
        context = build_routing_context(
            run_id="r",
            turn_index=1,
            messages=({"role": "user", "content": "ok"},),
            context_window_tokens=1000,
            run_purpose=purpose,
        )
        assert not should_ensemble(
            context,
            confidence=0.90,
            proposer_count=2,
            aggregator_available=True,
            proposer_provider_count=2,
            required_tier="C3",
        )
