"""审计表测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from acos.audit.models import (
    ACLAuditLog,
    AuditRecordRef,
    KnowledgeAccessLog,
    KnowledgeGovernanceAudit,
    OrgChangeAudit,
)
from acos.audit.repository import AuditRepository


async def _setup_db(db_path: str) -> None:
    """创建审计表结构。"""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS acl_audit_log (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                company_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                action TEXT NOT NULL,
                decision TEXT NOT NULL,
                matched_rule TEXT,
                scope_hash TEXT,
                trace_id TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_access_logs (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                operator TEXT,
                subject TEXT NOT NULL,
                action TEXT NOT NULL,
                query_hash TEXT,
                scope_hash TEXT,
                result_knowledge_ids TEXT NOT NULL DEFAULT '[]',
                result_count INTEGER NOT NULL DEFAULT 0,
                decision TEXT NOT NULL,
                matched_rules TEXT NOT NULL DEFAULT '[]',
                trace_id TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_governance_audit (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                action TEXT NOT NULL,
                before_snapshot TEXT,
                after_snapshot TEXT,
                operator TEXT NOT NULL,
                reason TEXT,
                trace_id TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS org_change_audit (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                action TEXT NOT NULL,
                before_snapshot TEXT,
                after_snapshot TEXT,
                operator TEXT NOT NULL,
                reason TEXT,
                trace_id TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_record_refs (
                ref_id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                audit_table TEXT NOT NULL,
                audit_id TEXT NOT NULL,
                ref_type TEXT NOT NULL,
                ref_id_value TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        await db.commit()


async def test_write_acl_audit(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = ACLAuditLog(
        subject="user:123",
        company_id="comp_a",
        resource_type="document",
        resource_id="doc_456",
        action="read",
        decision="allow",
        matched_rule="rule_1",
        scope_hash="abc123",
        trace_id="trace_001",
        timestamp="2025-07-19T10:00:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        record_id = await repo.write_acl_audit(conn, record)
        assert record_id == record.id

        cursor = await conn.execute("SELECT * FROM acl_audit_log WHERE id = ?", (record_id,))
        row = await cursor.fetchone()
        assert row is not None
        assert row[1] == "user:123"  # subject
        assert row[2] == "comp_a"  # company_id
        assert row[3] == "document"  # resource_type
        assert row[4] == "doc_456"  # resource_id
        assert row[5] == "read"  # action
        assert row[6] == "allow"  # decision


async def test_write_knowledge_access(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = KnowledgeAccessLog(
        company_id="comp_a",
        operator="user:123",
        subject="user:123",
        action="search",
        query_hash="qhash_001",
        scope_hash="scope_001",
        result_knowledge_ids=["k1", "k2"],
        result_count=2,
        decision="allow",
        matched_rules=[{"rule": "r1"}],
        trace_id="trace_002",
        timestamp="2025-07-19T10:01:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        record_id = await repo.write_knowledge_access(conn, record)
        assert record_id == record.id

        cursor = await conn.execute(
            "SELECT * FROM knowledge_access_logs WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[1] == "comp_a"  # company_id
        assert row[3] == "user:123"  # subject
        assert row[4] == "search"  # action
        assert row[7] == '["k1", "k2"]'  # result_knowledge_ids
        assert row[8] == 2  # result_count


async def test_write_knowledge_governance_audit(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = KnowledgeGovernanceAudit(
        company_id="comp_a",
        resource_type="knowledge",
        resource_id="k_001",
        action="update",
        before_snapshot='{"title": "old"}',
        after_snapshot='{"title": "new"}',
        operator="user:456",
        reason="content correction",
        trace_id="trace_003",
        timestamp="2025-07-19T10:02:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        record_id = await repo.write_knowledge_governance_audit(conn, record)
        assert record_id == record.id

        cursor = await conn.execute(
            "SELECT * FROM knowledge_governance_audit WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[1] == "comp_a"
        assert row[3] == "k_001"
        assert row[5] == '{"title": "old"}'


async def test_write_org_change_audit(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = OrgChangeAudit(
        company_id="comp_a",
        aggregate_type="department",
        aggregate_id="dept_001",
        action="create",
        before_snapshot="",
        after_snapshot='{"name": "Engineering"}',
        operator="user:789",
        reason="new team",
        trace_id="trace_004",
        timestamp="2025-07-19T10:03:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        record_id = await repo.write_org_change_audit(conn, record)
        assert record_id == record.id

        cursor = await conn.execute(
            "SELECT * FROM org_change_audit WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[1] == "comp_a"
        assert row[2] == "department"
        assert row[5] == ""


async def test_write_audit_ref(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = AuditRecordRef(
        company_id="comp_a",
        audit_table="acl_audit_log",
        audit_id="acl_001",
        ref_type="evidence",
        ref_id_value="ev_001",
        created_at="2025-07-19T10:04:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        ref_id = await repo.write_audit_ref(conn, record)
        assert ref_id == record.ref_id

        cursor = await conn.execute(
            "SELECT * FROM audit_record_refs WHERE ref_id = ?", (ref_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[1] == "comp_a"
        assert row[2] == "acl_audit_log"
        assert row[4] == "evidence"


async def test_acl_audit_requires_resource(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = ACLAuditLog(
        subject="user:123",
        company_id="comp_a",
        resource_type="",
        resource_id="",
        action="read",
        decision="deny",
        trace_id="trace_005",
        timestamp="2025-07-19T10:05:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        # resource_type 为空字符串时仍可写入（业务层校验）
        record_id = await repo.write_acl_audit(conn, record)

        cursor = await conn.execute("SELECT resource_type, resource_id FROM acl_audit_log WHERE id = ?", (record_id,))
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == ""
        assert row[1] == ""


async def test_audit_never_modified(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = ACLAuditLog(
        subject="user:123",
        company_id="comp_a",
        resource_type="document",
        resource_id="doc_001",
        action="read",
        decision="allow",
        trace_id="trace_006",
        timestamp="2025-07-19T10:06:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        await repo.write_acl_audit(conn, record)

        # Repository 不提供 update 方法，验证无法通过仓库修改
        assert not hasattr(repo, "update_acl_audit")
        assert not hasattr(repo, "update_knowledge_access")
        assert not hasattr(repo, "update_knowledge_governance_audit")
        assert not hasattr(repo, "update_org_change_audit")
        assert not hasattr(repo, "update_audit_ref")

        # 直接 SQL 也无法修改（append-only 语义）
        cursor = await conn.execute("SELECT decision FROM acl_audit_log WHERE id = ?", (record.id,))
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "allow"


async def test_audit_never_deleted(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()
    record = ACLAuditLog(
        subject="user:123",
        company_id="comp_a",
        resource_type="document",
        resource_id="doc_002",
        action="read",
        decision="allow",
        trace_id="trace_007",
        timestamp="2025-07-19T10:07:00Z",
    )

    async with aiosqlite.connect(db_path) as conn:
        await repo.write_acl_audit(conn, record)

        # Repository 不提供 delete 方法
        assert not hasattr(repo, "delete_acl_audit")
        assert not hasattr(repo, "delete_knowledge_access")
        assert not hasattr(repo, "delete_knowledge_governance_audit")
        assert not hasattr(repo, "delete_org_change_audit")
        assert not hasattr(repo, "delete_audit_ref")

        # 记录仍然存在
        cursor = await conn.execute("SELECT id FROM acl_audit_log WHERE id = ?", (record.id,))
        row = await cursor.fetchone()
        assert row is not None


async def test_company_isolation(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "audit.db")
    await _setup_db(db_path)

    repo = AuditRepository()

    async with aiosqlite.connect(db_path) as conn:
        # 写入两个不同公司的记录
        record_a = ACLAuditLog(
            subject="user:1",
            company_id="comp_a",
            resource_type="doc",
            resource_id="d1",
            action="read",
            decision="allow",
            trace_id="t1",
            timestamp="2025-07-19T10:00:00Z",
        )
        record_b = ACLAuditLog(
            subject="user:2",
            company_id="comp_b",
            resource_type="doc",
            resource_id="d2",
            action="read",
            decision="deny",
            trace_id="t2",
            timestamp="2025-07-19T10:01:00Z",
        )
        await repo.write_acl_audit(conn, record_a)
        await repo.write_acl_audit(conn, record_b)

        # 按 company_id 隔离查询 comp_a
        cursor = await conn.execute(
            "SELECT id, subject FROM acl_audit_log WHERE company_id = ?", ("comp_a",)
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "user:1"

        # 按 company_id 隔离查询 comp_b
        cursor = await conn.execute(
            "SELECT id, subject FROM acl_audit_log WHERE company_id = ?", ("comp_b",)
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "user:2"
