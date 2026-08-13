from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fake_provider import FakeProvider
from ibreeze.routing.context import build_routing_context
from ibreeze.routing.ensemble import EnsembleExecutor, EnsemblePlan
from ibreeze.runtime.model_loop import ModelTurn
from ibreeze.routing.engine import PlannedDeployment
from ibreeze.routing.types import RouteRole


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def _deployment(candidate_id: str, *, role: str = "single") -> PlannedDeployment:
    return PlannedDeployment(
        {
            "candidate_id": candidate_id,
            "provider_release_id": f"provider-{candidate_id}",
            "model_binding_id": f"model-{candidate_id}",
            "credential_ref": f"credential-{candidate_id}",
            "eligible_roles": [role],
        },
        1,
        RouteRole(role),
    )


def test_golden_manifest_is_complete_and_fingerprints_are_unique() -> None:
    manifest_path = FIXTURES / "routing-golden-tasks.v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = manifest["tasks"]
    assert len(tasks) == 200
    assert {task["tier"] for task in tasks} == {"C0", "C1", "C2", "C3"}
    assert all((ROOT / task["input_fixture"]).is_file() for task in tasks)
    fingerprints = {
        hashlib.sha256((ROOT / task["input_fixture"]).read_bytes()).hexdigest()
        for task in tasks
    }
    assert len(fingerprints) == 200


@pytest.mark.asyncio
async def test_fixed_fake_provider_has_one_call_and_no_tools() -> None:
    provider = FakeProvider()
    result = await provider.complete()
    assert result.content == "fake-provider:ok_single"
    assert provider.calls == 1
    assert provider.received_tool_names == [()]


@pytest.mark.asyncio
async def test_selective_ensemble_quorum_and_aggregator_tool_boundary() -> None:
    providers = {name: FakeProvider() for name in ("a", "b", "aggregator")}
    proposer_a = _deployment("a", role="proposer")
    proposer_b = _deployment("b", role="proposer")
    aggregator = _deployment("aggregator", role="aggregator")
    calls: list[tuple[str, tuple[str, ...]]] = []

    async def invoke(
        deployment: PlannedDeployment,
        _messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        candidate_id = str(deployment.candidate["candidate_id"])
        calls.append((candidate_id, tool_names))
        return await providers[candidate_id].complete(tool_names=tool_names)

    result = await EnsembleExecutor(grace_seconds=0).execute(
        EnsemblePlan(
            proposers=(proposer_a, proposer_b),
            aggregator=aggregator,
            quorum=2,
            proposer_timeout_seconds=10,
            aggregator_timeout_seconds=10,
        ),
        ({"role": "user", "content": "review"},),
        ("workspace.write",),
        invoke,
    )
    assert result.content.startswith("fake-provider")
    assert calls[:2] == [("a", ("workspace.write",)), ("b", ("workspace.write",))]
    assert calls[-1] == ("aggregator", ("workspace.write",))
    assert providers["a"].calls == providers["b"].calls == providers["aggregator"].calls == 1


@pytest.mark.asyncio
async def test_ensemble_cancel_leaves_no_pending_tasks() -> None:
    async def invoke(
        _deployment: PlannedDeployment,
        _messages: tuple[dict[str, object], ...],
        _tool_names: tuple[str, ...],
    ) -> ModelTurn:
        await asyncio.sleep(3600)
        return ModelTurn(content="unreachable")

    task = asyncio.create_task(
        EnsembleExecutor(grace_seconds=0).execute(
            EnsemblePlan(
                proposers=(_deployment("a", role="proposer"), _deployment("b", role="proposer")),
                aggregator=_deployment("aggregator", role="aggregator"),
                quorum=2,
                proposer_timeout_seconds=10,
                aggregator_timeout_seconds=10,
            ),
            ({"role": "user", "content": "cancel"},),
            (),
            invoke,
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
