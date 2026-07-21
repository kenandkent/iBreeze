"""6 处后端缺陷修复验证（SC / E2E 用例）。"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import pytest

from acos.rpc.errors import AcosError
from acos.rpc.methods_audit import AuditMethods
from acos.rpc.methods_org import OrganizationMethods
from acos.rpc.server import RPCServer
from acos.store.migrator import Migrator
from acos.task.service import TaskService
from tests.task.conftest import (
    migrated_db,
    seed_backend,
    seed_budget_policy,
    seed_company_employee,
)

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[1] / "migrations")


async def _migrated(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    await Migrator(db_path).run_pending_migrations(MIGRATIONS_DIR)
    return db_path


# ── SC-30-2: grant.list 过期标记 expired ──────────────────────────────

async def test_grant_list_marks_expired(tmp_path) -> None:
    db = await _migrated(tmp_path)
    methods = OrganizationMethods(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """INSERT INTO access_grants
               (grant_id, company_id, employee_id, target_type, target_id,
                permission, status, expires_at, approved_by)
               VALUES ('g1','c1','e1','task','t1','task_read','active',
                       '2000-01-01T00:00:00+00:00','system')"""
        )
        await conn.commit()
    res = await methods._grant_list({"company_id": "c1", "status": "active"})
    assert res["total"] == 1
    assert res["grants"][0]["expired"] is True


async def test_grant_list_active_not_expired(tmp_path) -> None:
    db = await _migrated(tmp_path)
    methods = OrganizationMethods(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """INSERT INTO access_grants
               (grant_id, company_id, employee_id, target_type, target_id,
                permission, status, expires_at, approved_by)
               VALUES ('g2','c1','e1','task','t1','task_read','active',
                       '2999-01-01T00:00:00+00:00','system')"""
        )
        await conn.commit()
    res = await methods._grant_list({"company_id": "c1", "status": "active"})
    assert "expired" not in res["grants"][0]


# ── SC-50-1: task.create 超预算 reject 拦截 ───────────────────────────

async def test_create_task_over_budget_rejected(migrated_db) -> None:
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    # per_task_limit=100, on_budget_exceeded='reject'
    await seed_budget_policy(db, per_task=100, on_exceeded="reject")
    svc = TaskService(db)
    with pytest.raises(AcosError) as exc:
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="company", goal="g", acceptance="a",
            budget={"currency": "USD", "limit_micros": 1_000_000},
        )
    assert exc.value.code == "WF-BUDGET-EXCEEDED"


async def test_create_task_within_budget_ok(migrated_db) -> None:
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db, per_task=100, on_exceeded="reject")
    svc = TaskService(db)
    res = await svc.create_task(
        company_id="co1", title="T", manager_employee_id="emp1",
        manager_scope="company", goal="g", acceptance="a",
        budget={"currency": "USD", "limit_micros": 50},
    )
    assert res["status"] == "created"


# ── SC-60-2: audit.query 兼容 type 与 audit_type ─────────────────────

async def test_audit_query_accepts_type_alias(tmp_path) -> None:
    db = await _migrated(tmp_path)
    methods = AuditMethods(db)
    # 不传 audit_type，只传 type='acl'，应不报非法取值
    res = await methods._audit_query({"company_id": "c1", "type": "acl"})
    assert "error" not in res
    assert res["audit_type"] == "acl"


# ── E2E-99 步骤1: 通用写方法幂等回填 ────────────────────────────────

async def test_dispatch_completes_idempotency(tmp_path) -> None:
    db = await _migrated(tmp_path)
    server = RPCServer(
        socket_path="/tmp/acos_e2e_test.sock",
        db_conn_factory=(lambda: aiosqlite.connect(db)),
    )
    captured: dict = {}

    async def _fake_handler(params):
        captured["called"] = captured.get("called", 0) + 1
        return {"ok": True, "n": params.get("n")}

    server.register_method("create.test", _fake_handler)

    req = {
        "type": "request", "id": "1", "method": "create.test",
        "params": {"n": 1, "_company_id": "c1", "_actor_type": "u", "_actor_id": "u1"},
        "idempotency_key": "k-1",
    }
    r1 = await server._dispatch(req)
    r2 = await server._dispatch(req)
    # handler 只应真正执行一次
    assert captured["called"] == 1
    assert r1["result"] == {"ok": True, "n": 1}
    assert r2["result"]["cached"] is True
    assert json.loads(r2["result"]["response_ref"]) == {"ok": True, "n": 1}


async def test_dispatch_completes_failed_idempotency(tmp_path) -> None:
    db = await _migrated(tmp_path)
    server = RPCServer(
        socket_path="/tmp/acos_e2e_test2.sock",
        db_conn_factory=(lambda: aiosqlite.connect(db)),
    )

    async def _boom(_params):
        raise AcosError(code="X-ERR", message="boom")

    server.register_method("create.boom", _boom)

    req = {
        "type": "request", "id": "1", "method": "create.boom",
        "params": {"_company_id": "c1", "_actor_type": "u", "_actor_id": "u1"},
        "idempotency_key": "k-err",
    }
    r1 = await server._dispatch(req)
    assert r1["error"]["code"] == "X-ERR"
    # 第二次相同 key 应命中缓存（failed 状态）
    r2 = await server._dispatch(req)
    assert r2["result"]["cached"] is True
    assert r2["result"]["status"] == "failed"


# ── E2E-99 步骤3: 公司软删后 list 不返回 ───────────────────────────

async def test_company_delete_soft_and_list_excludes(tmp_path) -> None:
    db = await _migrated(tmp_path)
    methods = OrganizationMethods(db)
    cid = (await methods._company_create({"name": "测试公司"}))["company_id"]
    # 需要 active 才能 dissolve；先 activate 再 delete
    await methods._company_activate({
        "company_id": cid, "expected_version": 1,
        "leader": {"name": "owner", "template_id": "tmpl-bootstrap"},
    })
    res = await methods._company_delete({"company_id": cid, "expected_version": 2})
    assert res["deleted"] is True
    # list 默认排除 dissolving / deleted
    lst = await methods._company_list({})
    assert all(c["company_id"] != cid for c in lst)
