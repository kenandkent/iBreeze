"""P8-T2 知识提炼流水线测试：密钥不进库、job 状态 CAS、citation 唯一、通知一致。"""

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
from acos.knowledge.extractor import Extractor, PolicyService, scrub_secrets
from acos.knowledge.models import KnowledgeDocument
from acos.knowledge.policy_service import PolicyService as PS
from acos.knowledge.service import KnowledgeService
from acos.providers.fake import FakeProviderAdapter
from acos.settings.service import SettingsService


class _Factory:
    async def create(self, resolved):
        return FakeProviderAdapter(provider_id=resolved.provider, models=[resolved.model])


async def _seed_doc(db_path, company_id, doc_id, content, source_record_id, category="manual"):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO knowledge_documents
                  (document_id, company_id, title, content, source_type, source_category,
                   visibility, embedding_status, checksum, version, status, source_record_id)
               VALUES (?, ?, 't', ?, 'manual', ?, 'company', 'pending', 'cs', 1, 'active', ?)""",
            (doc_id, company_id, content, category, source_record_id),
        )
        await db.commit()


def test_scrub_secrets_removes_key() -> None:
    text = "api_key = 'sk-1234567890abcdef' and password = \"hunter2secret\""
    out = scrub_secrets(text)
    assert "sk-1234567890abcdef" not in out
    assert "hunter2secret" not in out
    assert "REDACTED" in out


async def test_extract_manual_skips_provider_and_no_secret(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await seed_company(db_path)
    await insert_knowledge_source(db_path, "comp_a", "manual", "m1", "sr1")
    settings = SettingsService(db_path)
    ps = PS(settings)
    resolved = await ps.resolve("comp_a")
    notifier = []
    ex = Extractor(_Factory(), ps, notifier=lambda s, j: notifier.append((s, j)))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        raw = "password = 'supersecret123' 这是手动知识内容，不应含密钥"
        job_id = await ex.extract(
            db, company_id="comp_a", source_record_id="sr1",
            source_type="manual", source_id="m1", raw_text=raw,
            source_category="manual", resolved=resolved,
        )
        # 文档内容不应含密钥
        cur = await db.execute("SELECT content FROM knowledge_documents WHERE source_record_id='sr1'")
        doc = await cur.fetchone()
        assert doc is not None
        assert "supersecret123" not in doc["content"]
    assert ("succeeded", job_id) in notifier


async def test_extract_provider_failure_marks_retryable(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await seed_company(db_path)
    await insert_knowledge_source(db_path, "comp_a", "domain_event", "d1", "sr2")
    settings = SettingsService(db_path)
    ps = PS(settings)
    resolved = await ps.resolve("comp_a")

    class _BoomFactory:
        async def create(self, resolved):
            raise RuntimeError("provider down")

    notifier = []
    ex = Extractor(_BoomFactory(), ps, notifier=lambda s, j: notifier.append((s, j)))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        job_id = await ex.extract(
            db, company_id="comp_a", source_record_id="sr2",
            source_type="domain_event", source_id="d1", raw_text="原始事件内容",
            source_category="official", resolved=resolved,
        )
        cur = await db.execute(
            "SELECT status FROM knowledge_ingestion_jobs WHERE job_id=?", (job_id,)
        )
        status = (await cur.fetchone())["status"]
        assert status == "retryable"
    assert ("retryable", job_id) in notifier


async def test_extract_creates_citation_per_chunk(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await seed_company(db_path)
    await insert_knowledge_source(db_path, "comp_a", "domain_event", "d2", "sr3")
    settings = SettingsService(db_path)
    ps = PS(settings)
    resolved = await ps.resolve("comp_a")
    ex = Extractor(_Factory(), ps)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await ex.extract(
            db, company_id="comp_a", source_record_id="sr3",
            source_type="domain_event", source_id="d2",
            raw_text="第一段知识。第二段知识。第三段知识。第四段知识。",
            source_category="official", resolved=resolved,
        )
        cur = await db.execute(
            """SELECT c.chunk_id, c.citation_id FROM knowledge_citations c
               JOIN knowledge_chunks k ON k.chunk_id = c.chunk_id
               WHERE k.source_record_id='sr3'"""
        )
        rows = await cur.fetchall()
        # 每个 chunk 恰一条 citation
        chunk_ids = [r["chunk_id"] for r in rows]
        assert len(chunk_ids) == len(set(chunk_ids))
        assert len(rows) == len(chunk_ids)


async def test_ingest_retry_creates_new_attempt(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await seed_company(db_path)
    await insert_knowledge_source(db_path, "comp_a", "domain_event", "d3", "sr4")
    await _seed_doc(db_path, "comp_a", "doc-r", "retry raw text content", "sr4")
    settings = SettingsService(db_path)
    ps = PS(settings)
    resolved = await ps.resolve("comp_a")
    ex = Extractor(_Factory(), ps)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        job_id = await ex.create_job(db, "comp_a", "sr4", "domain_event", "d3", resolved)
        await ex._cas_status(db, job_id, "pending", "failed")
        new_job = await ex.retry_job(
            db, job_id, resolved, "retry raw text content", "official"
        )
        cur = await db.execute(
            "SELECT attempt, status FROM knowledge_ingestion_jobs WHERE job_id=?", (new_job,)
        )
        row = await cur.fetchone()
        assert row["attempt"] == 2
        assert row["status"] == "succeeded"
