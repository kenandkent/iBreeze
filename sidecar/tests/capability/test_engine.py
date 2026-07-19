"""CapabilityEngine 测试。"""

from __future__ import annotations

import pytest

from acos.capability.engine import CapabilityEngine, ResolvedRunConfig
from acos.rpc.errors import AcosError


@pytest.fixture
def engine() -> CapabilityEngine:
    return CapabilityEngine()


def _snapshot(
    cap_id: str = "cap-1",
    version: int = 1,
    checksum: str = "",
    **extra: object,
) -> dict:
    data: dict = {
        "capability_id": cap_id,
        "version": version,
        "snapshot_checksum": checksum,
        "prompt_segments": {"system": "You are helpful."},
        "tools": [{"name": "read_file"}, {"name": "write_file"}],
        "knowledge_scope": {"refs": [{"knowledge_id": "k-1"}, {"knowledge_id": "k-2"}]},
        "model": {"provider": "openai", "model": "gpt-4", "tier": "premium"},
        "review_spec": {"enabled": False},
        "decision_limits": {"max_cost_per_run": 100},
        "security_policy": {"allow_network": True},
        "backend_requirements": ["gpu"],
    }
    data.update(extra)
    return data


def _employee(**extra: object) -> dict:
    base: dict = {"employee_id": "emp-1", "name": "Alice"}
    base.update(extra)
    return base


def _scope(**extra: object) -> dict:
    base: dict = {"allowed_tools": ["read_file", "write_file"], "allowed_knowledge_ids": ["k-1", "k-2"]}
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_resolve_returns_resolved_run_config(engine: CapabilityEngine) -> None:
    snap = _snapshot(checksum="")
    result = await engine.resolve(_employee(), {}, snap, _scope())
    assert isinstance(result, ResolvedRunConfig)
    assert result.employee_id == "emp-1"
    assert result.capability_id == "cap-1"
    assert result.capability_version == 1
    assert result.config_hash


@pytest.mark.asyncio
async def test_system_prompt_from_segments(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    result = await engine.resolve(_employee(), {}, snap, _scope())
    assert result.system_prompt == "You are helpful."


@pytest.mark.asyncio
async def test_system_prompt_fallback_to_snapshot_key(engine: CapabilityEngine) -> None:
    snap = _snapshot(prompt_segments={})
    snap["system_prompt"] = "Fallback prompt"
    result = await engine.resolve(_employee(), {}, snap, _scope())
    assert result.system_prompt == "Fallback prompt"


@pytest.mark.asyncio
async def test_tool_set_filtered_by_scope(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    scope = _scope(allowed_tools=["read_file"])
    result = await engine.resolve(_employee(), {}, snap, scope)
    tool_names = [t["name"] for t in result.tool_set]
    assert tool_names == ["read_file"]


@pytest.mark.asyncio
async def test_tool_set_no_filter(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    scope = _scope(allowed_tools=[])
    result = await engine.resolve(_employee(), {}, snap, scope)
    assert len(result.tool_set) == 2


@pytest.mark.asyncio
async def test_knowledge_scope_filtered(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    scope = _scope(allowed_knowledge_ids=["k-1"])
    result = await engine.resolve(_employee(), {}, snap, scope)
    refs = result.knowledge_scope.get("refs", [])
    assert len(refs) == 1
    assert refs[0]["knowledge_id"] == "k-1"


@pytest.mark.asyncio
async def test_model_tier_override(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    scope = _scope(model_tier_override="budget")
    result = await engine.resolve(_employee(), {}, snap, scope)
    assert result.model["tier"] == "budget"


@pytest.mark.asyncio
async def test_model_default_when_empty(engine: CapabilityEngine) -> None:
    snap = _snapshot(model={})
    result = await engine.resolve(_employee(), {}, snap, _scope())
    assert result.model["provider"] == "default"


@pytest.mark.asyncio
async def test_review_spec_force_review(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    scope = _scope(force_review=True)
    result = await engine.resolve(_employee(), {}, snap, scope)
    assert result.review_spec["enabled"] is True


@pytest.mark.asyncio
async def test_decision_limits_merged(engine: CapabilityEngine) -> None:
    snap = _snapshot(decision_limits={"max_cost_per_run": 50, "max_tokens": 4096})
    scope = _scope(decision_limits={"max_tool_calls": 10})
    result = await engine.resolve(_employee(), {}, snap, scope)
    assert result.decision_limits["max_cost_per_run"] == 50
    assert result.decision_limits["max_tokens"] == 4096
    assert result.decision_limits["max_tool_calls"] == 10


@pytest.mark.asyncio
async def test_security_policy_restrictions(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    scope = _scope(security_restrictions={"allow_network": False})
    result = await engine.resolve(_employee(), {}, snap, scope)
    assert result.security_policy["allow_network"] is False


@pytest.mark.asyncio
async def test_backend_requirements_union(engine: CapabilityEngine) -> None:
    snap = _snapshot(backend_requirements=["gpu"])
    scope = _scope(backend_requirements=["ssd", "gpu"])
    result = await engine.resolve(_employee(), {}, snap, scope)
    assert set(result.backend_requirements) == {"gpu", "ssd"}


@pytest.mark.asyncio
async def test_context_sections_built(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    task_ctx = {"user_input": "hello", "runtime_variables": {"a": "b"}}
    result = await engine.resolve(_employee(), task_ctx, snap, _scope())
    assert len(result.context_sections) == 6
    names = [s["name"] for s in result.context_sections]
    assert names == [
        "employee_identity",
        "workflow_context",
        "capability_context",
        "retrieved_knowledge",
        "runtime_variables",
        "user_input",
    ]


@pytest.mark.asyncio
async def test_snapshot_checksum_validation_passes(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    computed = engine._compute_snapshot_checksum(snap)
    snap["snapshot_checksum"] = computed
    result = await engine.resolve(_employee(), {}, snap, _scope())
    assert result.snapshot_checksum == computed


@pytest.mark.asyncio
async def test_snapshot_checksum_validation_fails(engine: CapabilityEngine) -> None:
    snap = _snapshot(checksum="wrong-checksum")
    with pytest.raises(AcosError) as exc_info:
        await engine.resolve(_employee(), {}, snap, _scope())
    assert exc_info.value.code == "CAP-SNAPSHOT-CHECKSUM-MISMATCH"


@pytest.mark.asyncio
async def test_config_hash_deterministic(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    r1 = await engine.resolve(_employee(), {}, snap, _scope())
    r2 = await engine.resolve(_employee(), {}, snap, _scope())
    assert r1.config_hash == r2.config_hash


@pytest.mark.asyncio
async def test_config_hash_changes_with_different_input(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    r1 = await engine.resolve(_employee(), {}, snap, _scope())
    r2 = await engine.resolve(_employee(employee_id="emp-2"), {}, snap, _scope())
    assert r1.config_hash != r2.config_hash


@pytest.mark.asyncio
async def test_workspace_from_scope(engine: CapabilityEngine) -> None:
    snap = _snapshot()
    scope = _scope(workspace_root="/tmp/ws", workspace_types=["code", "docs"])
    result = await engine.resolve(_employee(), {}, snap, scope)
    assert result.workspace["workspace_root"] == "/tmp/ws"
    assert result.workspace["workspace_types"] == ["code", "docs"]
