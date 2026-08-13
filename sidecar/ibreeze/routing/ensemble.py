"""Deterministic selective-ensemble planning and safe aggregation helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ibreeze.routing.context import RoutingContext
from ibreeze.routing.engine import PlannedDeployment
from ibreeze.runtime.model_loop import ModelTurn


@dataclass(frozen=True, slots=True)
class EnsemblePlan:
    proposers: tuple[PlannedDeployment, ...]
    aggregator: PlannedDeployment
    quorum: int
    proposer_timeout_seconds: int
    aggregator_timeout_seconds: int
    proposer_max_retries: int = 0


def _diversity_score(candidate: dict[str, Any], anchor: dict[str, Any]) -> Decimal:
    """Return the fixed orthogonality score from the routing contract."""
    score = Decimal("0")
    if candidate.get("provider_release_id") != anchor.get("provider_release_id"):
        score += Decimal("0.30")
    if candidate.get("model_vendor") != anchor.get("model_vendor"):
        score += Decimal("0.25")
    if candidate.get("model_family") != anchor.get("model_family"):
        score += Decimal("0.25")
    candidate_arch = candidate.get("architecture_class")
    anchor_arch = anchor.get("architecture_class")
    if candidate_arch != "unknown" and anchor_arch != "unknown" and candidate_arch != anchor_arch:
        score += Decimal("0.20")
    return score


def _quality_decimal(candidate: dict[str, Any]) -> Decimal:
    try:
        return Decimal(str(candidate.get("quality_prior", "0.5000")))
    except Exception:
        return Decimal("0.5000")


def select_proposer_candidates(
    scored: list[tuple[Decimal, dict[str, Any]]],
    *,
    max_proposers: int,
    required_tier: str,
) -> tuple[tuple[dict[str, Any], str], ...]:
    """Select the deterministic anchor/diversity/critic/sanity lineup.

    ``scored`` is already calculated with the single-model score.  The
    returned role labels are envelope metadata only; all physical requests
    still use the authorized ``proposer`` route role.
    """
    if max_proposers <= 0 or not scored:
        return ()
    ordered = sorted(
        scored,
        key=lambda pair: (
            -pair[0],
            -_quality_decimal(pair[1]),
            int(pair[1].get("latency_prior_ms", 3000)),
            str(pair[1].get("model_binding_id", "")),
            str(pair[1].get("candidate_id", "")),
        ),
    )
    anchor = ordered[0][1]
    selected: list[tuple[dict[str, Any], str]] = [(anchor, "anchor")]
    remaining = ordered[1:]
    if max_proposers >= 2 and remaining:
        orthogonal = sorted(
            remaining,
            key=lambda pair: (
                -_diversity_score(pair[1], anchor),
                -pair[0],
                -_quality_decimal(pair[1]),
                int(pair[1].get("latency_prior_ms", 3000)),
                str(pair[1].get("model_binding_id", "")),
                str(pair[1].get("candidate_id", "")),
            ),
        )[0]
        selected.append((orthogonal[1], "orthogonal_reviewer"))
        remaining = [pair for pair in remaining if pair[1] is not orthogonal[1]]
    if max_proposers >= 3 and remaining:
        critic = sorted(
            remaining,
            key=lambda pair: (
                -_quality_decimal(pair[1]),
                -pair[0],
                int(pair[1].get("latency_prior_ms", 3000)),
                str(pair[1].get("model_binding_id", "")),
                str(pair[1].get("candidate_id", "")),
            ),
        )[0]
        selected.append((critic[1], "strong_critic"))
        remaining = [pair for pair in remaining if pair[1] is not critic[1]]
    if max_proposers >= 4 and required_tier == "C3" and remaining:
        sanity = min(
            remaining,
            key=lambda pair: (
                int(pair[1].get("latency_prior_ms", 3000)),
                -pair[0],
                str(pair[1].get("model_binding_id", "")),
                str(pair[1].get("candidate_id", "")),
            ),
        )
        selected.append((sanity[1], "fast_sanity"))
    return tuple(selected[:max_proposers])


def default_quorum(proposer_count: int) -> int:
    if proposer_count < 2 or proposer_count > 4:
        raise ValueError("ROUTING_ENSEMBLE_PROPOSER_COUNT_INVALID")
    return {2: 2, 3: 2, 4: 3}[proposer_count]


def should_ensemble(
    context: RoutingContext,
    *,
    confidence: float,
    proposer_count: int,
    aggregator_available: bool,
    estimated_input_tokens: int | None = None,
    aggregator_context_window: int | None = None,
    max_proposers: int = 3,
    proposer_provider_count: int = 0,
    vision_proposer_count: int | None = None,
    aggregator_supports_vision: bool = True,
    force_ensemble: bool = False,
    required_tier: str | None = None,
) -> bool:
    if not aggregator_available or proposer_count < 2:
        return False
    if context.attachment_types and (not aggregator_supports_vision or (vision_proposer_count is not None and vision_proposer_count < 2)):
        return False
    if context.provider_failures >= 2 and proposer_provider_count < 2 and not force_ensemble:
        return False
    triggered = (
        force_ensemble
        or context.verification_failures >= 1
        or getattr(context, "open_blocker_high_count", 0) >= 1
        or (context.provider_failures >= 2 and proposer_provider_count >= 2)
        or ((required_tier or getattr(context, "previous_tier", None)) == "C3" and confidence < 0.70)
        or ((required_tier or getattr(context, "previous_tier", None)) == "C2" and confidence < 0.55)
    )
    if not triggered:
        return False
    if estimated_input_tokens is not None and aggregator_context_window is not None:
        upper_bound = estimated_input_tokens + 2000 + max_proposers * 24000
        if aggregator_context_window < upper_bound:
            return False
    return True


def candidate_envelope(candidate_id: str, role: str, turn: ModelTurn, *, max_chars: int = 24000) -> dict[str, Any]:
    content = turn.content or ""
    truncated = len(content) > max_chars
    return {
        "candidate_id": candidate_id,
        "role": role,
        "content": content[:max_chars],
        "suggested_tool_calls": [{"name": call.name, "arguments": call.arguments} for call in turn.tool_calls],
        "truncated": truncated,
    }


class EnsembleExecutor:
    def __init__(self, *, grace_seconds: float = 5.0) -> None:
        self.grace_seconds = grace_seconds

    async def execute(
        self,
        plan: EnsemblePlan,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
        invoke: Callable[[PlannedDeployment, tuple[dict[str, object], ...], tuple[str, ...]], Awaitable[ModelTurn]],
    ) -> ModelTurn:
        if len(plan.proposers) < 2 or len(plan.proposers) > 4:
            raise ValueError("ROUTING_ENSEMBLE_PROPOSER_COUNT_INVALID")
        if plan.quorum < default_quorum(len(plan.proposers)) or plan.quorum > len(plan.proposers):
            raise ValueError("ROUTING_ENSEMBLE_INVALID")

        async def run(proposer: PlannedDeployment) -> ModelTurn:
            # Proposers receive tool names/schemas as non-executable context.
            # Their returned tool calls are retained in the envelope only;
            # this executor never invokes the tool runtime for proposer output.
            attempts = max(0, int(plan.proposer_max_retries)) + 1
            last_error: BaseException | None = None
            for attempt in range(attempts):
                try:
                    return await asyncio.wait_for(invoke(proposer, messages, tool_names), timeout=plan.proposer_timeout_seconds)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    last_error = exc
                    if attempt + 1 >= attempts or bool(getattr(exc, "visible_content", False)):
                        raise
            assert last_error is not None
            raise last_error

        tasks = [asyncio.create_task(run(proposer)) for proposer in plan.proposers]
        pending: set[asyncio.Task[ModelTurn]] = set(tasks)
        result_by_index: dict[int, ModelTurn | BaseException] = {}
        deadline = asyncio.get_running_loop().time() + plan.proposer_timeout_seconds
        try:
            while pending:
                remaining = max(0.0, deadline - asyncio.get_running_loop().time())
                if remaining == 0:
                    break
                done, pending = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    index = tasks.index(task)
                    try:
                        result_by_index[index] = task.result()
                    except BaseException as exc:
                        result_by_index[index] = exc
                successful = sum(isinstance(value, ModelTurn) for value in result_by_index.values())
                if successful >= plan.quorum:
                    if pending:
                        grace_done, pending = await asyncio.wait(
                            pending,
                            timeout=min(max(0.0, self.grace_seconds), 5.0),
                        )
                        for task in grace_done:
                            index = tasks.index(task)
                            try:
                                result_by_index[index] = task.result()
                            except BaseException as exc:
                                result_by_index[index] = exc
                    break
        except asyncio.CancelledError:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        results = [result_by_index.get(index, RuntimeError("ROUTING_ENSEMBLE_PROPOSER_TIMEOUT")) for index in range(len(tasks))]
        envelopes = [
            candidate_envelope(str(plan.proposers[index].candidate.get("candidate_id")), "proposer", result)
            for index, result in enumerate(results)
            if isinstance(result, ModelTurn)
        ]
        if len(envelopes) < plan.quorum:
            raise RuntimeError("ROUTING_ENSEMBLE_QUORUM_NOT_MET")
        packed = json.dumps(
            {
                "type": "ibreeze.routing.proposals.v1",
                "proposals": envelopes,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        aggregate_messages = messages + ({"role": "user", "content": packed},)
        attempts = 2
        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(
                    invoke(plan.aggregator, aggregate_messages, tool_names), timeout=plan.aggregator_timeout_seconds
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt + 1 >= attempts or bool(getattr(exc, "visible_content", False)):
                    raise
                kind = getattr(exc, "kind", "")
                if kind not in {"RATE_LIMITED", "PROVIDER_OVERLOADED", "TRANSPORT_TRANSIENT", "TIMEOUT", "INVALID_RESPONSE"}:
                    raise
        raise RuntimeError("ROUTING_AGGREGATOR_RETRY_EXHAUSTED")
