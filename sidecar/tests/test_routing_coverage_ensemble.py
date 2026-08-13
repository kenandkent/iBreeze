from __future__ import annotations

import asyncio

import pytest

from ibreeze.routing.context import build_routing_context
from ibreeze.routing.engine import PlannedDeployment
from ibreeze.routing.ensemble import EnsembleExecutor, EnsemblePlan, default_quorum, select_proposer_candidates, should_ensemble
from ibreeze.routing.types import RouteRole
from ibreeze.runtime.model_loop import ModelTurn


def _candidate(cid: str, provider: str, *, vendor: str = "v1", family: str = "f1", arch: str = "dense", quality: float = 0.5, latency: int = 100):
    return {
        "candidate_id": cid,
        "provider_release_id": provider,
        "model_vendor": vendor,
        "model_family": family,
        "architecture_class": arch,
        "quality_prior": quality,
        "latency_prior_ms": latency,
    }


def _deployment(cid: str, role: RouteRole) -> PlannedDeployment:
    return PlannedDeployment({"candidate_id": cid}, 1, role)


def test_diversity_score_accumulates_orthogonal_dimensions() -> None:
    anchor = _candidate("a", "p1", vendor="v1", family="f1", arch="dense")
    # Same provider as anchor (provider branch not taken) but every other
    # dimension differs.
    same_provider = _candidate("b", "p1", vendor="v2", family="f2", arch="mlp")
    lineup = select_proposer_candidates(
        [(0.9, anchor), (0.85, same_provider)],
        max_proposers=4,
        required_tier="C3",
    )
    assert lineup[0] == (anchor, "anchor")
    assert lineup[1] == (same_provider, "orthogonal_reviewer")


def test_quality_decimal_falls_back_on_bad_value() -> None:
    bad_quality = _candidate("e", "p9", quality="not-a-number")
    lineup = select_proposer_candidates([(0.5, bad_quality)], max_proposers=4, required_tier="C3")
    assert lineup[0][0] is bad_quality
    assert lineup[0][0]["quality_prior"] == "not-a-number"


def test_select_proposer_candidates_empty_and_single() -> None:
    assert select_proposer_candidates([], max_proposers=3, required_tier="C3") == ()
    assert select_proposer_candidates([(0.9, _candidate("a", "p1"))], max_proposers=0, required_tier="C3") == ()
    assert select_proposer_candidates([(0.9, _candidate("a", "p1"))], max_proposers=1, required_tier="C3") == (
        (_candidate("a", "p1"), "anchor"),
    )


def test_select_proposer_candidates_full_lineup_with_sanity() -> None:
    anchor = _candidate("a", "p1", vendor="v1", family="f1", arch="dense", quality=0.95, latency=200)
    orthogonal = _candidate("b", "p1", vendor="v2", family="f2", arch="mlp", quality=0.90, latency=100)
    critic = _candidate("c", "p9", vendor="v1", family="f1", arch="dense", quality=0.85, latency=150)
    sanity = _candidate("d", "p1", vendor="v1", family="f1", arch="dense", quality=0.70, latency=50)
    extra = _candidate("e", "p9", vendor="v1", family="f1", arch="dense", quality=0.60, latency=250)
    lineup = select_proposer_candidates(
        [
            (0.60, extra),
            (0.70, sanity),
            (0.80, critic),
            (0.90, orthogonal),
            (0.95, anchor),
        ],
        max_proposers=4,
        required_tier="C3",
    )
    assert [item["candidate_id"] for item, _role in lineup] == ["a", "b", "c", "d"]
    assert [role for _item, role in lineup] == ["anchor", "orthogonal_reviewer", "strong_critic", "fast_sanity"]


def test_default_quorum_rejects_out_of_range_counts() -> None:
    with pytest.raises(ValueError, match="ROUTING_ENSEMBLE_PROPOSER_COUNT_INVALID"):
        default_quorum(1)
    with pytest.raises(ValueError, match="ROUTING_ENSEMBLE_PROPOSER_COUNT_INVALID"):
        default_quorum(5)


def test_should_ensemble_gates_and_bounds() -> None:
    context = build_routing_context(run_id="r", turn_index=1, messages=({"role": "user", "content": "ok"},), context_window_tokens=1000)
    assert not should_ensemble(context, confidence=0.5, proposer_count=2, aggregator_available=False)
    assert not should_ensemble(context, confidence=0.5, proposer_count=1, aggregator_available=True)
    attachment_context = build_routing_context(
        run_id="r", turn_index=1, messages=({"role": "user", "content": "ok"},), context_window_tokens=1000, attachment_types=("image",)
    )
    assert not should_ensemble(
        attachment_context,
        confidence=0.5,
        proposer_count=2,
        aggregator_available=True,
        aggregator_supports_vision=False,
    )
    assert not should_ensemble(
        attachment_context,
        confidence=0.5,
        proposer_count=2,
        aggregator_available=True,
        vision_proposer_count=1,
    )
    failure_context = build_routing_context(
        run_id="r", turn_index=1, messages=({"role": "user", "content": "ok"},), context_window_tokens=1000, provider_failures=2
    )
    assert not should_ensemble(
        failure_context,
        confidence=0.5,
        proposer_count=2,
        aggregator_available=True,
        proposer_provider_count=1,
    )


def test_should_ensemble_true_without_window_bounds() -> None:
    context = build_routing_context(
        run_id="r", turn_index=1, messages=({"role": "user", "content": "repair"},), context_window_tokens=1000, run_purpose="repair"
    )
    assert should_ensemble(
        context,
        confidence=0.5,
        proposer_count=2,
        aggregator_available=True,
        estimated_input_tokens=None,
        aggregator_context_window=None,
        required_tier="C3",
    )


class _KindError(Exception):
    def __init__(self, kind: str, *, visible: bool = False) -> None:
        super().__init__(kind)
        self.kind = kind
        self.visible_content = visible


@pytest.mark.asyncio
async def test_executor_rejects_invalid_plan_shape() -> None:
    async def invoke(deployment, _messages, _tools):
        return ModelTurn(content="x")

    executor = EnsembleExecutor()
    with pytest.raises(ValueError, match="ROUTING_ENSEMBLE_PROPOSER_COUNT_INVALID"):
        await executor.execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER),),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=2,
                aggregator_timeout_seconds=2,
            ),
            (),
            (),
            invoke,
        )
    with pytest.raises(ValueError, match="ROUTING_ENSEMBLE_INVALID"):
        await executor.execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=1,
                proposer_timeout_seconds=2,
                aggregator_timeout_seconds=2,
            ),
            (),
            (),
            invoke,
        )


@pytest.mark.asyncio
async def test_executor_retries_transient_proposer_failure() -> None:
    calls: dict[str, int] = {}

    async def invoke(deployment, _messages, _tools):
        cid = deployment.candidate["candidate_id"]
        calls[cid] = calls.get(cid, 0) + 1
        if deployment.role is RouteRole.PROPOSER and cid == "a" and calls[cid] == 1:
            raise RuntimeError("transient")
        if deployment.role is RouteRole.AGGREGATOR:
            return ModelTurn(content="final")
        return ModelTurn(content="proposal")

    result = await EnsembleExecutor(grace_seconds=0).execute(
        EnsemblePlan(
            proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
            aggregator=_deployment("g", RouteRole.AGGREGATOR),
            quorum=2,
            proposer_timeout_seconds=2,
            aggregator_timeout_seconds=2,
            proposer_max_retries=1,
        ),
        ({"role": "user", "content": "x"},),
        (),
        invoke,
    )
    assert result.content == "final"
    assert calls["a"] == 2
    assert calls["b"] == 1


@pytest.mark.asyncio
async def test_executor_handles_cancelled_proposer() -> None:
    async def invoke(deployment, _messages, _tools):
        raise asyncio.CancelledError

    with pytest.raises(RuntimeError, match="ROUTING_ENSEMBLE_QUORUM_NOT_MET"):
        await EnsembleExecutor(grace_seconds=0).execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=1,
                aggregator_timeout_seconds=1,
            ),
            (),
            (),
            invoke,
        )


@pytest.mark.asyncio
async def test_executor_grace_period_waits_for_slow_proposer() -> None:
    async def invoke(deployment, _messages, _tools):
        if deployment.candidate["candidate_id"] == "slow":
            await asyncio.sleep(0.05)
        if deployment.role is RouteRole.AGGREGATOR:
            return ModelTurn(content="final")
        return ModelTurn(content="proposal")

    result = await EnsembleExecutor(grace_seconds=1.0).execute(
        EnsemblePlan(
            proposers=(
                _deployment("fast", RouteRole.PROPOSER),
                _deployment("slow", RouteRole.PROPOSER),
                _deployment("fast2", RouteRole.PROPOSER),
            ),
            aggregator=_deployment("g", RouteRole.AGGREGATOR),
            quorum=2,
            proposer_timeout_seconds=2,
            aggregator_timeout_seconds=2,
        ),
        ({"role": "user", "content": "x"},),
        (),
        invoke,
    )
    assert result.content == "final"


@pytest.mark.asyncio
async def test_executor_grace_period_collects_failed_proposer() -> None:
    async def invoke(deployment, _messages, _tools):
        if deployment.candidate["candidate_id"] == "slow-fail":
            await asyncio.sleep(0.05)
            raise RuntimeError("boom")
        if deployment.role is RouteRole.AGGREGATOR:
            return ModelTurn(content="final")
        return ModelTurn(content="proposal")

    result = await EnsembleExecutor(grace_seconds=1.0).execute(
        EnsemblePlan(
            proposers=(
                _deployment("fast", RouteRole.PROPOSER),
                _deployment("fast2", RouteRole.PROPOSER),
                _deployment("slow-fail", RouteRole.PROPOSER),
            ),
            aggregator=_deployment("g", RouteRole.AGGREGATOR),
            quorum=2,
            proposer_timeout_seconds=2,
            aggregator_timeout_seconds=2,
        ),
        ({"role": "user", "content": "x"},),
        (),
        invoke,
    )
    assert result.content == "final"


@pytest.mark.asyncio
async def test_executor_cancellation_cancels_pending_proposers() -> None:
    async def invoke(deployment, _messages, _tools):
        await asyncio.sleep(10)
        return ModelTurn(content="x")

    executor = EnsembleExecutor(grace_seconds=1.0)
    task = asyncio.create_task(
        executor.execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=30,
                aggregator_timeout_seconds=30,
            ),
            (),
            (),
            invoke,
        )
    )
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_executor_times_out_hanging_proposers() -> None:
    async def invoke(deployment, _messages, _tools):
        await asyncio.sleep(10)
        return ModelTurn(content="x")

    with pytest.raises(RuntimeError, match="ROUTING_ENSEMBLE_QUORUM_NOT_MET"):
        await EnsembleExecutor(grace_seconds=0).execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=1,
                aggregator_timeout_seconds=1,
            ),
            (),
            (),
            invoke,
        )


@pytest.mark.asyncio
async def test_executor_aggregator_retryable_and_non_retryable_failures() -> None:
    async def proposer_success(deployment, _messages, _tools):
        return ModelTurn(content="proposal")

    # Retryable failure on both attempts -> re-raise the last attempt error.
    aggregator_attempts = {"count": 0}

    async def retryable_aggregator(deployment, _messages, _tools):
        aggregator_attempts["count"] += 1
        raise _KindError("RATE_LIMITED")

    with pytest.raises(_KindError):
        await EnsembleExecutor(grace_seconds=0).execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=2,
                aggregator_timeout_seconds=2,
            ),
            (),
            (),
            lambda deployment, messages, tools: retryable_aggregator(deployment, messages, tools)
            if deployment.role is RouteRole.AGGREGATOR
            else proposer_success(deployment, messages, tools),
        )
    assert aggregator_attempts["count"] == 2

    # Non-retryable kind raises immediately.
    async def hard_fail_aggregator(deployment, _messages, _tools):
        raise _KindError("BOGUS_KIND")

    with pytest.raises(_KindError):
        await EnsembleExecutor(grace_seconds=0).execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=2,
                aggregator_timeout_seconds=2,
            ),
            (),
            (),
            lambda deployment, messages, tools: hard_fail_aggregator(deployment, messages, tools)
            if deployment.role is RouteRole.AGGREGATOR
            else proposer_success(deployment, messages, tools),
        )

    # A visible-content failure is never retried.
    async def visible_fail_aggregator(deployment, _messages, _tools):
        raise _KindError("RATE_LIMITED", visible=True)

    with pytest.raises(_KindError):
        await EnsembleExecutor(grace_seconds=0).execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=2,
                aggregator_timeout_seconds=2,
            ),
            (),
            (),
            lambda deployment, messages, tools: visible_fail_aggregator(deployment, messages, tools)
            if deployment.role is RouteRole.AGGREGATOR
            else proposer_success(deployment, messages, tools),
        )


@pytest.mark.asyncio
async def test_executor_aggregator_cancellation_propagates() -> None:
    async def invoke(deployment, _messages, _tools):
        if deployment.role is RouteRole.PROPOSER:
            return ModelTurn(content="proposal")
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await EnsembleExecutor(grace_seconds=0).execute(
            EnsemblePlan(
                proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
                aggregator=_deployment("g", RouteRole.AGGREGATOR),
                quorum=2,
                proposer_timeout_seconds=2,
                aggregator_timeout_seconds=2,
            ),
            (),
            (),
            invoke,
        )
