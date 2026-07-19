"""cap.engine.resolve 测试：覆盖四分支 knowledge_scope 逐分支只收窄 ACL，
六类来源类别下推，证明任何组合不扩大权限。

直接测试 CapabilityEngine.resolve（RPC 仅薄封装），与 test_engine.py 互补。
"""

from __future__ import annotations

import pytest

from acos.capability.engine import CapabilityEngine
from acos.rpc.errors import AcosError


@pytest.fixture
def engine() -> CapabilityEngine:
    return CapabilityEngine()


def _snapshot(visibility_scope: dict, source_categories: list[str] | None = None, **extra: object) -> dict:
    data: dict = {
        "capability_id": "cap-1",
        "version": 1,
        "snapshot_checksum": "",
        "knowledge_scope": {
            "visibility_scope": visibility_scope,
            "source_categories": source_categories if source_categories is not None else [],
        },
    }
    data.update(extra)
    return data


def _scope(**extra: object) -> dict:
    base: dict = {
        "visible_department_ids": ["D1", "D2", "D3"],
        "visible_task_ids": ["T1", "T2"],
        "own_employee_id": "E1",
        "private_visible_employee_ids": ["E2", "E3"],
    }
    base.update(extra)
    return base


# ── 四分支只收窄（不扩大） ─────────────────────────────────


@pytest.mark.asyncio
async def test_capability_company_only_excludes_other_branches(
    engine: CapabilityEngine,
) -> None:
    snap = _snapshot({"company": True, "department": False, "task": False, "employee": False})
    scope = _scope()
    result = await engine.resolve({}, {}, snap, scope)
    acl = result.knowledge_scope["acl"]
    assert acl["company"] is True
    # 即便 ACL 覆盖了全部门/任务/员工，能力未声明则一律为空
    assert acl["department"] == []
    assert acl["task"] == []
    assert acl["employee"] == []


@pytest.mark.asyncio
async def test_capability_task_only_narrows_to_task_branch(
    engine: CapabilityEngine,
) -> None:
    snap = _snapshot({"company": False, "department": False, "task": True, "employee": False})
    scope = _scope()
    result = await engine.resolve({}, {}, snap, scope)
    acl = result.knowledge_scope["acl"]
    assert acl["company"] is False
    assert acl["department"] == []
    assert acl["task"] == ["T1", "T2"]
    assert acl["employee"] == []


@pytest.mark.asyncio
async def test_capability_employee_only_uses_own_and_private(
    engine: CapabilityEngine,
) -> None:
    snap = _snapshot({"company": False, "department": False, "task": False, "employee": True})
    # ACL 含很宽的部门，但 employee 分支只应包含本人与 private_visible
    scope = _scope()
    result = await engine.resolve({}, {}, snap, scope)
    acl = result.knowledge_scope["acl"]
    assert acl["employee"] == ["E1", "E2", "E3"]
    # 不得因 visible_department_ids 很宽而把整个部门 employee_private 打开
    assert "D1" not in acl["employee"]
    assert acl["department"] == []


@pytest.mark.asyncio
async def test_capability_all_branches_narrows_per_branch(
    engine: CapabilityEngine,
) -> None:
    snap = _snapshot({"company": True, "department": True, "task": True, "employee": True})
    scope = _scope()
    result = await engine.resolve({}, {}, snap, scope)
    acl = result.knowledge_scope["acl"]
    assert acl["company"] is True
    assert acl["department"] == ["D1", "D2", "D3"]
    assert acl["task"] == ["T1", "T2"]
    assert acl["employee"] == ["E1", "E2", "E3"]


# ── 六类来源类别下推 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_source_categories_passthrough(engine: CapabilityEngine) -> None:
    cats = ["artifact", "standard", "conversation", "report", "file", "manual"]
    snap = _snapshot(
        {"company": True, "department": False, "task": False, "employee": False},
        source_categories=cats,
    )
    result = await engine.resolve({}, {}, snap, _scope())
    assert result.knowledge_scope["source_categories"] == cats


@pytest.mark.asyncio
async def test_source_categories_subset_narrows(engine: CapabilityEngine) -> None:
    snap = _snapshot(
        {"company": True, "department": False, "task": False, "employee": False},
        source_categories=["manual"],
    )
    result = await engine.resolve({}, {}, snap, _scope())
    # 只能收窄，不能扩大为全部
    assert result.knowledge_scope["source_categories"] == ["manual"]


# ── 校验和 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checksum_mismatch_raises(engine: CapabilityEngine) -> None:
    snap = _snapshot(
        {"company": True, "department": False, "task": False, "employee": False},
    )
    snap["snapshot_checksum"] = "bad"
    with pytest.raises(AcosError) as exc_info:
        await engine.resolve({}, {}, snap, _scope())
    assert exc_info.value.code == "CAP-SNAPSHOT-CHECKSUM-MISMATCH"


# ── 配置哈希稳定 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_hash_deterministic(engine: CapabilityEngine) -> None:
    snap = _snapshot({"company": True, "department": True, "task": True, "employee": True})
    r1 = await engine.resolve({}, {}, snap, _scope())
    r2 = await engine.resolve({}, {}, snap, _scope())
    assert r1.config_hash == r2.config_hash
