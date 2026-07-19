"""gov.* RPC 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.governance.budget import BudgetService
from acos.governance.service import GovernanceService
from acos.rpc.methods_gov import GovMethods
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
    GovMethods(db_path).register_to(srv)
    return srv


async def _seed_task(db_path: str, task_id: str, company_id: str) -> None:
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO tasks (task_id, company_id, title, status, version) VALUES (?, ?, 't', 'created', 1)",
            (task_id, company_id),
        )
        await db.commit()


async def _seed_company_policy(db_path: str, company_id: str, on_budget_exceeded: str = "pause") -> None:
    svc = GovernanceService(db_path)
    await svc.create_budget_policy(
        __import__("acos.governance.models", fromlist=["BudgetPolicy"]).BudgetPolicy(
            company_id=company_id, name="default", monthly_limit=1_000_000, currency="USD",
            on_budget_exceeded=on_budget_exceeded,
        )
    )


async def test_budget_policy_version_cas(db_path: str, server: RPCServer) -> None:
    company_id = "comp-cas"
    await _seed_company_policy(db_path, company_id)
    get0 = await server._handlers["gov.budgetPolicy.get"]({"company_id": company_id})
    assert get0["exists"] is True
    v0 = get0["version"]

    upd = await server._handlers["gov.budgetPolicy.update"](
        {
            "company_id": company_id,
            "expected_policy_version": v0,
            "updates": {"monthly_limit": 2_000_000},
            "idempotency_key": "ik-1",
        }
    )
    assert upd["version"] == v0 + 1
    assert upd["monthly_limit"] == 2_000_000

    # 旧版本 CAS 冲突
    with pytest.raises(Exception):
        await server._handlers["gov.budgetPolicy.update"](
            {
                "company_id": company_id,
                "expected_policy_version": v0,
                "updates": {"monthly_limit": 3_000_000},
                "idempotency_key": "ik-2",
            }
        )

    # 旧版本被 supersede，active 是新版
    get1 = await server._handlers["gov.budgetPolicy.get"]({"company_id": company_id})
    assert get1["version"] == v0 + 1
    assert get1["monthly_limit"] == 2_000_000


async def test_budget_policy_currency_rejected(db_path: str, server: RPCServer) -> None:
    company_id = "comp-cur"
    await _seed_company_policy(db_path, company_id)
    get0 = await server._handlers["gov.budgetPolicy.get"]({"company_id": company_id})
    with pytest.raises(Exception):
        await server._handlers["gov.budgetPolicy.update"](
            {
                "company_id": company_id,
                "expected_policy_version": get0["version"],
                "updates": {"currency": "XXX"},
                "idempotency_key": "ik-cur",
            }
        )


async def test_budget_policy_overflow_rejected(db_path: str, server: RPCServer) -> None:
    company_id = "comp-of"
    await _seed_company_policy(db_path, company_id)
    get0 = await server._handlers["gov.budgetPolicy.get"]({"company_id": company_id})
    with pytest.raises(Exception):
        await server._handlers["gov.budgetPolicy.update"](
            {
                "company_id": company_id,
                "expected_policy_version": get0["version"],
                "updates": {"monthly_limit": 10_000_000_000_000_000_000_000},
                "idempotency_key": "ik-of",
            }
        )


async def test_approval_type_crud(db_path: str, server: RPCServer) -> None:
    company_id = "comp-at"
    created = await server._handlers["gov.approvalType.create"](
        {
            "company_id": company_id,
            "name": "高风险计划",
            "category": "plan_approval",
            "requires_risk_summary": True,
            "idempotency_key": "ik-at",
        }
    )
    assert created["approval_type_id"].startswith("at-")
    listed = await server._handlers["gov.approvalType.list"]({"company_id": company_id})
    assert len(listed["types"]) == 1
    assert listed["types"][0]["category"] == "plan_approval"

    got = await server._handlers["gov.approvalType.get"](
        {"approval_type_id": created["approval_type_id"]}
    )
    assert got["name"] == "高风险计划"


async def test_budget_get_aggregates(db_path: str, server: RPCServer) -> None:
    company_id = "comp-bg"
    await _seed_company_policy(db_path, company_id)
    task_id = "task-bg"
    await _seed_task(db_path, task_id, company_id)
    budget = BudgetService(db_path)
    await budget.ensure_task_budget(company_id, task_id, "USD", 1_000_000)

    res = await server._handlers["gov.budget.get"]({"task_id": task_id, "company_id": company_id})
    assert res["limit_micros"] == 1_000_000
    assert res["remaining_micros"] == 1_000_000

    # 跨公司拒绝
    await _seed_task(db_path, "task-bg2", "other-co")
    with pytest.raises(Exception):
        await server._handlers["gov.budget.get"]({"task_id": "task-bg2", "company_id": company_id})


async def test_budget_revision_lock_wf_pending(db_path: str, server: RPCServer) -> None:
    company_id = "comp-br"
    await _seed_company_policy(db_path, company_id, on_budget_exceeded="require_approval")
    task_id = "task-br"
    await _seed_task(db_path, task_id, company_id)
    budget = BudgetService(db_path)
    await budget.ensure_task_budget(company_id, task_id, "USD", 100)

    # 预留 80 成功
    r1 = await server._handlers["gov.budget.reserve"](
        {"company_id": company_id, "task_id": task_id, "run_id": "r1", "currency": "USD", "amount_micros": 80}
    )
    assert r1["status"] == "reserved"

    # 再预留 50 触顶 -> 创建 budget_approval + lock，返回 pending_approval
    r2 = await server._handlers["gov.budget.reserve"](
        {"company_id": company_id, "task_id": task_id, "run_id": "r2", "currency": "USD", "amount_micros": 50}
    )
    assert r2["status"] == "pending_approval"
    approval_id = r2["approval_id"]

    # pending 期间同任务同币种新 reservation 返回 WF-BUDGET-APPROVAL-PENDING
    r3 = await server._handlers["gov.budget.reserve"](
        {"company_id": company_id, "task_id": task_id, "run_id": "r3", "currency": "USD", "amount_micros": 10}
    )
    assert r3["status"] == "blocked"
    assert r3["code"] == "WF-BUDGET-APPROVAL-PENDING"

    # 批准预算审批 -> limit 提升，lock 释放
    await server._handlers["approval.resolve"]({}) if False else None
    from acos.rpc.methods_approval import ApprovalMethods

    app_server = RPCServer(db_conn_factory=lambda: __import__("aiosqlite").connect(db_path))
    ApprovalMethods(db_path).register_to(app_server)
    res = await app_server._handlers["approval.resolve"](
        {"approval_id": approval_id, "decision": "approve", "expected_version": 1, "idempotency_key": "ik-res"}
    )
    assert res["status"] == "approved"

    svc = GovernanceService(db_path)
    after = await budget.get_task_budget(task_id, company_id)
    assert after["limit_micros"] == 150  # 100 + 50
    assert not await svc.has_active_budget_revision_lock(task_id, "USD")


async def test_audit_query(db_path: str, server: RPCServer) -> None:
    company_id = "comp-au"
    await _seed_company_policy(db_path, company_id)
    await server._handlers["gov.budgetPolicy.update"](
        {
            "company_id": company_id,
            "expected_policy_version": 1,
            "updates": {"monthly_limit": 5_000_000},
            "idempotency_key": "ik-au",
        }
    )
    q = await server._handlers["gov.audit.query"]({"company_id": company_id, "type": "budget"})
    assert q["total"] >= 1
    assert q["items"][0]["category"] == "budget"


async def test_budget_reserve_downgrade(db_path: str, server: RPCServer) -> None:
    """预算触顶 on_budget_exceeded=downgrade 时返回 downgrade 信号。"""
    company_id = "comp-down"
    await _seed_company_policy(db_path, company_id, on_budget_exceeded="downgrade")
    await _seed_task(db_path, "t-dn", company_id)
    # 直接用 BudgetService 创建任务预算
    from acos.governance.budget import BudgetService
    budget_svc = BudgetService(db_path)
    await budget_svc.ensure_task_budget(
        company_id=company_id, task_id="t-dn", currency="USD", limit_micros=100,
    )
    # 预留 50（够用）
    r1 = await server._handlers["gov.budget.reserve"](
        {"company_id": company_id, "task_id": "t-dn", "run_id": "r1", "currency": "USD", "amount_micros": 50}
    )
    assert r1["status"] == "reserved"
    # 再预留 60（超限）→ 应返回 downgrade
    r2 = await server._handlers["gov.budget.reserve"](
        {"company_id": company_id, "task_id": "t-dn", "run_id": "r2", "currency": "USD", "amount_micros": 60}
    )
    assert r2["status"] == "downgrade"
    assert r2["code"] == "WF-BUDGET-DOWNGRADE"
