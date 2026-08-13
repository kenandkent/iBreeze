from __future__ import annotations

import pytest

from ibreeze.routing.engine import PlannedDeployment
from ibreeze.routing.ensemble import EnsembleExecutor, EnsemblePlan, candidate_envelope
from ibreeze.routing.types import RouteRole
from ibreeze.runtime.model_loop import ModelTurn, ToolCall


def _deployment(cid: str, role: RouteRole) -> PlannedDeployment:
    return PlannedDeployment({"candidate_id": cid}, 1, role)


@pytest.mark.asyncio
async def test_proposer_tool_calls_are_enveloped_and_aggregator_gets_tools() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    async def invoke(deployment, _messages, tools):
        calls.append((deployment.candidate["candidate_id"], tools))
        if deployment.role is RouteRole.PROPOSER:
            return ModelTurn(content="proposal", tool_calls=(ToolCall(id="p", name="write", arguments={}),))
        return ModelTurn(content="final", tool_calls=(ToolCall(id="a", name="write", arguments={}),))

    result = await EnsembleExecutor(grace_seconds=0).execute(
        EnsemblePlan(
            proposers=(_deployment("a", RouteRole.PROPOSER), _deployment("b", RouteRole.PROPOSER)),
            aggregator=_deployment("g", RouteRole.AGGREGATOR),
            quorum=2,
            proposer_timeout_seconds=2,
            aggregator_timeout_seconds=2,
        ),
        ({"role": "user", "content": "x"},),
        ("write",),
        invoke,
    )
    assert result.content == "final"
    assert calls[:2] == [("a", ("write",)), ("b", ("write",))]
    assert calls[-1] == ("g", ("write",))
    envelope = candidate_envelope("a", "anchor", ModelTurn(content="x" * 24001))
    assert envelope["truncated"] is True
    assert len(envelope["content"]) == 24000


@pytest.mark.asyncio
async def test_quorum_not_met_does_not_call_aggregator() -> None:
    calls = 0

    async def invoke(deployment, _messages, _tools):
        nonlocal calls
        calls += 1
        if deployment.role is RouteRole.PROPOSER:
            raise RuntimeError("failed")
        return ModelTurn(content="unexpected")

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
    assert calls == 2
