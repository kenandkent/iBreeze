"""approval.* RPC 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.governance.service import GovernanceService
from acos.rpc.methods_approval import ApprovalMethods
from acos.rpc.server import RPCServer
from acos.store.migrator import Migrator

MIGRATIONS = str(Path(__file__).resolve().parents[2] / "migrations")


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    migrator = Migrator(str(p))
    await migrator.run_pending_migrations(MIGRATIONS)
    return str(p)


@pytest.fixture
def server(db_path: str) -> RPCServer:
    srv = RPCServer(db_conn_factory=lambda: __import__("aiosqlite").connect(db_path))
    ApprovalMethods(db_path).register_to(srv)
    return srv


async def _seed_task(db_path: str, task_id: str, company_id: str) -> None:
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO tasks (task_id, company_id, title, status, version) VALUES (?, ?, 't', 'created', 1)",
            (task_id, company_id),
        )
        await db.commit()


async def test_approval_request_lifecycle(db_path: str, server: RPCServer) -> None:
    company_id = "comp-life"
    await _seed_task(db_path, "task-life", company_id)
    out = await server._handlers["approval.request"](
        {
            "company_id": company_id,
            "approval_type": "plan_approval",
            "target_ref": "generation:gen-1",
            "risk_summary": "包含高风险节点",
            "task_id": "task-life",
            "idempotency_key": "ik-req",
        }
    )
    assert out["status"] == "pending"
    approval_id = out["approval_id"]

    got = await server._handlers["approval.get"]({"approval_id": approval_id})
    assert got["status"] == "pending"
    assert got["approval_type"] == "plan_approval"

    listed = await server._handlers["approval.list"]({"company_id": company_id})
    assert listed["total"] == 1

    res = await server._handlers["approval.resolve"](
        {"approval_id": approval_id, "decision": "approve", "expected_version": 1, "idempotency_key": "ik-res"}
    )
    assert res["status"] == "approved"

    got2 = await server._handlers["approval.get"]({"approval_id": approval_id})
    assert got2["status"] == "approved"


async def test_concurrent_approve_only_one_succeeds(db_path: str, server: RPCServer) -> None:
    company_id = "comp-conc"
    await _seed_task(db_path, "task-conc", company_id)
    out = await server._handlers["approval.request"](
        {
            "company_id": company_id,
            "approval_type": "tool_call",
            "target_ref": "tool:node-1",
            "task_id": "task-conc",
            "idempotency_key": "ik-conc-req",
        }
    )
    approval_id = out["approval_id"]

    # 两个并发 approve，第一个成功，第二个版本冲突
    res1 = await server._handlers["approval.resolve"](
        {"approval_id": approval_id, "decision": "approve", "expected_version": 1, "idempotency_key": "ik-c1"}
    )
    assert res1["status"] == "approved"
    with pytest.raises(Exception):
        await server._handlers["approval.resolve"](
            {"approval_id": approval_id, "decision": "approve", "expected_version": 1, "idempotency_key": "ik-c2"}
        )


async def test_expired_approval_cannot_resolve(db_path: str, server: RPCServer) -> None:
    company_id = "comp-exp"
    await _seed_task(db_path, "task-exp", company_id)
    out = await server._handlers["approval.request"](
        {
            "company_id": company_id,
            "approval_type": "tool_call",
            "target_ref": "tool:node-x",
            "task_id": "task-exp",
            "expiry": "2000-01-01T00:00:00+00:00",
            "idempotency_key": "ik-exp-req",
        }
    )
    approval_id = out["approval_id"]
    with pytest.raises(Exception):
        await server._handlers["approval.resolve"](
            {"approval_id": approval_id, "decision": "approve", "expected_version": 1, "idempotency_key": "ik-exp"}
        )


async def test_reject_then_resolve_fails(db_path: str, server: RPCServer) -> None:
    company_id = "comp-rej"
    await _seed_task(db_path, "task-rej", company_id)
    out = await server._handlers["approval.request"](
        {
            "company_id": company_id,
            "approval_type": "tool_call",
            "target_ref": "tool:node-y",
            "task_id": "task-rej",
            "idempotency_key": "ik-rej-req",
        }
    )
    approval_id = out["approval_id"]
    res = await server._handlers["approval.resolve"](
        {"approval_id": approval_id, "decision": "reject", "comment": "不安全", "expected_version": 1, "idempotency_key": "ik-rej"}
    )
    assert res["status"] == "rejected"
    with pytest.raises(Exception):
        await server._handlers["approval.resolve"](
            {"approval_id": approval_id, "decision": "approve", "expected_version": 2, "idempotency_key": "ik-rej2"}
        )


async def test_resolve_not_found(db_path: str, server: RPCServer) -> None:
    with pytest.raises(Exception):
        await server._handlers["approval.resolve"](
            {"approval_id": "ap-nope", "decision": "approve", "idempotency_key": "ik-nf"}
        )


async def test_budget_approval_applies_limit(db_path: str, server: RPCServer) -> None:
    from acos.governance.budget import BudgetService
    from acos.governance.models import BudgetPolicy

    company_id = "comp-ba"
    svc = GovernanceService(db_path)
    await svc.create_budget_policy(BudgetPolicy(company_id=company_id, name="d", monthly_limit=1_000_000, currency="USD"))
    await _seed_task(db_path, "task-ba", company_id)
    budget = BudgetService(db_path)
    await budget.ensure_task_budget(company_id, "task-ba", "USD", 100)

    out = await server._handlers["approval.request"](
        {
            "company_id": company_id,
            "approval_type": "budget_approval",
            "target_ref": "budget:task-ba",
            "task_id": "task-ba",
            "currency": "USD",
            "current_limit_micros": 100,
            "requested_delta_micros": 200,
            "requested_limit_micros": 300,
            "usage_watermark_micros": 0,
            "idempotency_key": "ik-ba-req",
        }
    )
    approval_id = out["approval_id"]
    res = await server._handlers["approval.resolve"](
        {"approval_id": approval_id, "decision": "approve", "expected_version": 1, "idempotency_key": "ik-ba-res"}
    )
    assert res["status"] == "approved"

    after = await budget.get_task_budget("task-ba", company_id)
    assert after["limit_micros"] == 300
    assert not await svc.has_active_budget_revision_lock("task-ba", "USD")
