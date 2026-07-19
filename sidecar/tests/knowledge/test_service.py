"""P8-T4a kg.* RPC 测试：越权拒绝、confirm 审计 operator=LocalOwner、ingest retry。"""

from __future__ import annotations

import aiosqlite
import pytest

from tests.knowledge._helpers import (
    insert_department,
    insert_knowledge_source,
    make_employee,
    seed_company,
    setup_db,
)
from acos.knowledge.extractor import Extractor, PolicyService
from acos.knowledge.models import KnowledgeDocument
from acos.knowledge.service import KnowledgeService
from acos.providers.fake import FakeProviderAdapter
from acos.rpc.methods_kg import KgMethods
from acos.settings.service import SettingsService


class _Factory:
    async def create(self, resolved):
        return FakeProviderAdapter(provider_id=resolved.provider, models=[resolved.model])


async def _seed_doc(db_path, company_id, doc_id, title, content, category="manual", vis="company"):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO knowledge_documents
                  (document_id, company_id, title, content, source_type, source_category,
                   visibility, embedding_status, checksum, version, status)
               VALUES (?, ?, ?, ?, 'manual', ?, ?, 'pending', 'cs', 1, 'active')""",
            (doc_id, company_id, title, content, category, vis),
        )
        await db.commit()


async def _seed_org(db_path):
    await seed_company(db_path, "comp_a")
    await seed_company(db_path, "comp_b")
    await insert_department(db_path, "comp_a", "D1", None)
    await insert_department(db_path, "comp_b", "BD1", None)
    await make_employee(db_path, "comp_a", "D1", "emp_a")
    await make_employee(db_path, "comp_b", "BD1", "emp_b")


async def test_document_get_cross_company_denied(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await _seed_org(db_path)
    await _seed_doc(db_path, "comp_a", "doc1", "A 文档", "内容")
    methods = KgMethods(db_path)
    res = await methods._document_get({
        "company_id": "comp_b", "view_as_employee_id": "emp_b", "knowledge_id": "doc1",
    })
    assert res.get("error") == "KG-NOT-FOUND" or res.get("error")


async def test_knowledge_confirm_audits_local_owner(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await _seed_org(db_path)
    await _seed_doc(db_path, "comp_a", "doc1", "A 文档", "内容")
    methods = KgMethods(db_path)
    res = await methods._knowledge_confirm({"company_id": "comp_a", "knowledge_id": "doc1"})
    assert res["governance_confirmed"] is True
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT operator, operator_type, action, target_id FROM knowledge_governance_audit WHERE target_id='doc1'"
        )
        row = await cur.fetchone()
        assert row is not None
        assert row["operator_type"] == "local_owner"
        assert row["action"] == "knowledge_confirm"


async def test_knowledge_reject_sets_status(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await _seed_org(db_path)
    await _seed_doc(db_path, "comp_a", "doc1", "A 文档", "内容")
    methods = KgMethods(db_path)
    res = await methods._knowledge_reject({"company_id": "comp_a", "knowledge_id": "doc1", "reason": "错误"})
    assert res["status"] == "rejected"
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT status FROM knowledge_documents WHERE document_id='doc1'")
        assert (await cur.fetchone())[0] == "rejected"


async def test_ingest_retry_only_retryable(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await _seed_org(db_path)
    await insert_knowledge_source(db_path, "comp_a", "domain_event", "d1", "sr1")
    await _seed_doc(db_path, "comp_a", "doc_r", "retry raw text", "内容")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """UPDATE knowledge_documents SET source_record_id='sr1' WHERE document_id='doc_r'"""
        )
        # 改 doc_r 的 source_record_id 关联，并构造一个 succeeded job
        await db.execute(
            """INSERT INTO knowledge_ingestion_jobs
                  (job_id, company_id, source_record_id, source_type, source_id, policy_id,
                   policy_version, attempt, status, version)
               VALUES ('job1','comp_a','sr1','domain_event','d1','','1',1,'succeeded',1)"""
        )
        await db.commit()
    methods = KgMethods(db_path)
    res = await methods._ingest_retry({"company_id": "comp_a", "job_id": "job1"})
    # succeeded 不可重试
    assert res.get("error") == "KG-EXTRACT-FAILED"


async def test_ingest_retry_cross_company_denied(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await _seed_org(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO knowledge_ingestion_jobs
                  (job_id, company_id, source_record_id, source_type, source_id, policy_id,
                   policy_version, attempt, status, version)
               VALUES ('jobX','comp_b','srX','domain_event','dX','','1',1,'retryable',1)"""
        )
        await db.commit()
    methods = KgMethods(db_path)
    res = await methods._ingest_retry({"company_id": "comp_a", "job_id": "jobX"})
    assert res.get("error") == "ORG-PERM-DENIED"


async def test_reindex_rebuilds_vectors(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await _seed_org(db_path)
    await _seed_doc(db_path, "comp_a", "doc1", "A 文档", "内容")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO knowledge_chunks
                  (chunk_id, document_id, company_id, content, chunk_index, embedding_status)
               VALUES ('ck1','doc1','comp_a','分块内容',0,'pending')"""
        )
        await db.commit()
    methods = KgMethods(db_path)
    res = await methods._reindex({"company_id": "comp_a"})
    assert res["reindexed"] == 1
    assert res["generation_id"]
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT embedding_status FROM knowledge_chunks WHERE chunk_id='ck1'")
        row = await cur.fetchone()
        assert row["embedding_status"] == "indexed"


async def test_reindex_requires_company(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    methods = KgMethods(db_path)
    try:
        await methods._reindex({})
        assert False, "应抛错"
    except Exception as exc:
        assert "company_id" in str(exc)
