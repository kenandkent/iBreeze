"""audit / intervention 查询 RPC 测试。"""

from __future__ import annotations

import os
import tempfile

import aiosqlite
import pytest

from acos.rpc.methods_audit import AuditMethods
from acos.rpc.server import RPCServer
from acos.store.migrator import Migrator

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "migrations")


@pytest.fixture
async def audit_methods() -> AuditMethods:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        migrator = Migrator(db_path)
        await migrator.run_pending_migrations(MIGRATIONS_DIR)
        methods = AuditMethods(db_path)
        yield methods
    finally:
        os.unlink(db_path)


async def _insert_intervention(
    methods: AuditMethods,
    *,
    company_id: str,
    status: str,
    target_ref: str,
    subtype: str = "approval",
    seq: int = 0,
) -> None:
    conn = await aiosqlite.connect(methods._db_path)
    try:
        await conn.execute(
            """INSERT INTO human_interventions
               (intervention_id, company_id, subtype, target_ref, status,
                allowed_actions, trace_id, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, '[]', ?, 1, ?, ?)""",
            (
                f"iv-{company_id}-{seq}",
                company_id,
                subtype,
                target_ref,
                status,
                f"trace-{seq}",
                f"2025-07-19T10:{seq:02d}:00Z",
                f"2025-07-19T10:{seq:02d}:00Z",
            ),
        )
        await conn.commit()
    finally:
        await conn.close()


async def _insert_acl(
    methods: AuditMethods, *, company_id: str, seq: int, ts: str
) -> None:
    conn = await aiosqlite.connect(methods._db_path)
    try:
        await conn.execute(
            """INSERT INTO acl_audit_log
               (id, subject, company_id, resource_type, resource_id,
                action, decision, trace_id, timestamp)
               VALUES (?, ?, ?, 'doc', ?, 'read', 'allow', ?, ?)""",
            (f"acl-{company_id}-{seq}", "user:x", company_id,
             f"res-{seq}", f"trace-{seq}", ts),
        )
        await conn.commit()
    finally:
        await conn.close()


async def _insert_org(
    methods: AuditMethods, *, company_id: str, seq: int, ts: str
) -> None:
    conn = await aiosqlite.connect(methods._db_path)
    try:
        await conn.execute(
            """INSERT INTO org_change_audit
               (id, company_id, aggregate_type, aggregate_id, action,
                before_snapshot, after_snapshot, operator, trace_id, timestamp)
               VALUES (?, ?, 'department', ?, 'create', '', '{}', 'user:x', ?, ?)""",
            (f"org-{company_id}-{seq}", company_id, f"agg-{seq}",
             f"trace-{seq}", ts),
        )
        await conn.commit()
    finally:
        await conn.close()


async def _insert_gov(
    methods: AuditMethods, *, company_id: str, seq: int, ts: str
) -> None:
    conn = await aiosqlite.connect(methods._db_path)
    try:
        await conn.execute(
            """INSERT INTO governance_audit
               (audit_id, company_id, category, aggregate_id, action,
                before_snapshot, after_snapshot, operator, trace_id, timestamp)
               VALUES (?, ?, 'budget', ?, 'create', '', '{}', 'user:x', ?, ?)""",
            (f"gov-{company_id}-{seq}", company_id, f"agg-{seq}",
             f"trace-{seq}", ts),
        )
        await conn.commit()
    finally:
        await conn.close()


class TestAuditMethods:
    async def test_register(self, audit_methods: AuditMethods) -> None:
        server = RPCServer()
        audit_methods.register_to(server)
        assert "intervention.list" in server._handlers
        assert "audit.query" in server._handlers

    # ── intervention.list ──

    async def test_intervention_missing_company(
        self, audit_methods: AuditMethods
    ) -> None:
        with pytest.raises(Exception):
            await audit_methods._intervention_list({})

    async def test_intervention_filter_status_and_isolation(
        self, audit_methods: AuditMethods
    ) -> None:
        await _insert_intervention(
            audit_methods, company_id="comp-a", status="open", target_ref="t1", seq=1
        )
        await _insert_intervention(
            audit_methods, company_id="comp-a", status="resolved", target_ref="t2", seq=2
        )
        await _insert_intervention(
            audit_methods, company_id="comp-b", status="open", target_ref="t3", seq=3
        )

        # comp-a 全部
        res = await audit_methods._intervention_list({"company_id": "comp-a"})
        assert res["total"] == 2
        assert res["page"] == 1
        assert res["limit"] == 20
        assert {i["target_ref"] for i in res["items"]} == {"t1", "t2"}

        # comp-a 仅 open
        res = await audit_methods._intervention_list(
            {"company_id": "comp-a", "status": "open"}
        )
        assert res["total"] == 1
        assert res["items"][0]["target_ref"] == "t1"

        # comp-b 隔离
        res = await audit_methods._intervention_list({"company_id": "comp-b"})
        assert res["total"] == 1
        assert res["items"][0]["company_id"] == "comp-b"

    async def test_intervention_pagination(
        self, audit_methods: AuditMethods
    ) -> None:
        for i in range(5):
            await _insert_intervention(
                audit_methods, company_id="comp-a", status="open",
                target_ref=f"t{i}", seq=i + 1,
            )
        res = await audit_methods._intervention_list(
            {"company_id": "comp-a", "page": 2, "limit": 2}
        )
        assert res["total"] == 5
        assert res["page"] == 2
        assert res["limit"] == 2
        assert len(res["items"]) == 2

    async def test_intervention_invalid_status(
        self, audit_methods: AuditMethods
    ) -> None:
        with pytest.raises(Exception):
            await audit_methods._intervention_list(
                {"company_id": "comp-a", "status": "bogus"}
            )

    # ── audit.query ──

    async def test_audit_query_missing_company(
        self, audit_methods: AuditMethods
    ) -> None:
        with pytest.raises(Exception):
            await audit_methods._audit_query({"audit_type": "acl"})

    async def test_audit_query_invalid_type(
        self, audit_methods: AuditMethods
    ) -> None:
        with pytest.raises(Exception):
            await audit_methods._audit_query(
                {"company_id": "comp-a", "audit_type": "bogus"}
            )

    async def test_audit_query_routing_and_isolation(
        self, audit_methods: AuditMethods
    ) -> None:
        # acl 表：comp-a 2 条，comp-b 1 条
        await _insert_acl(audit_methods, company_id="comp-a", seq=1, ts="2025-07-19T10:00:00Z")
        await _insert_acl(audit_methods, company_id="comp-a", seq=2, ts="2025-07-19T11:00:00Z")
        await _insert_acl(audit_methods, company_id="comp-b", seq=1, ts="2025-07-19T10:00:00Z")
        # org / governance 表
        await _insert_org(audit_methods, company_id="comp-a", seq=1, ts="2025-07-19T10:00:00Z")
        await _insert_gov(audit_methods, company_id="comp-a", seq=1, ts="2025-07-19T10:00:00Z")

        # 路由到 acl，仅 comp-a
        res = await audit_methods._audit_query(
            {"company_id": "comp-a", "audit_type": "acl"}
        )
        assert res["total"] == 2
        assert res["audit_type"] == "acl"
        assert all(i["company_id"] == "comp-a" for i in res["items"])

        # 路由到 org
        res = await audit_methods._audit_query(
            {"company_id": "comp-a", "audit_type": "org"}
        )
        assert res["total"] == 1

        # 路由到 governance
        res = await audit_methods._audit_query(
            {"company_id": "comp-a", "audit_type": "governance"}
        )
        assert res["total"] == 1

        # 跨公司隔离：comp-b 在 acl 只能看到自己的 1 条
        res = await audit_methods._audit_query(
            {"company_id": "comp-b", "audit_type": "acl"}
        )
        assert res["total"] == 1

    async def test_audit_query_time_range_and_pagination(
        self, audit_methods: AuditMethods
    ) -> None:
        await _insert_acl(audit_methods, company_id="comp-a", seq=1, ts="2025-07-19T08:00:00Z")
        await _insert_acl(audit_methods, company_id="comp-a", seq=2, ts="2025-07-19T10:00:00Z")
        await _insert_acl(audit_methods, company_id="comp-a", seq=3, ts="2025-07-19T12:00:00Z")

        res = await audit_methods._audit_query(
            {
                "company_id": "comp-a",
                "audit_type": "acl",
                "start_at": "2025-07-19T09:00:00Z",
                "end_at": "2025-07-19T11:00:00Z",
                "page": 1,
                "limit": 10,
            }
        )
        assert res["total"] == 1
        assert res["items"][0]["resource_id"] == "res-2"

        # 分页
        res = await audit_methods._audit_query(
            {"company_id": "comp-a", "audit_type": "acl", "page": 1, "limit": 2}
        )
        assert res["total"] == 3
        assert len(res["items"]) == 2

    async def test_audit_query_inverted_time_range(
        self, audit_methods: AuditMethods
    ) -> None:
        with pytest.raises(Exception):
            await audit_methods._audit_query(
                {
                    "company_id": "comp-a",
                    "audit_type": "acl",
                    "start_at": "2025-07-19T12:00:00Z",
                    "end_at": "2025-07-19T08:00:00Z",
                }
            )
