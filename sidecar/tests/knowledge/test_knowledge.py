"""知识库测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from acos.knowledge.embedding import EmbeddingService
from acos.knowledge.models import KnowledgeDocument
from acos.knowledge.service import KnowledgeService

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_path TEXT,
    source_category TEXT NOT NULL DEFAULT 'custom',
    visibility TEXT NOT NULL DEFAULT 'company',
    embedding_generation_id TEXT,
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    checksum TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_company ON knowledge_documents(company_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_category
  ON knowledge_documents(company_id, source_category);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES knowledge_documents(document_id),
    company_id TEXT NOT NULL,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc ON knowledge_chunks(document_id);
"""


async def _setup_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_CREATE_SQL)
        await db.commit()


async def test_create_document(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "knowledge.db")
    await _setup_db(db_path)

    svc = KnowledgeService()
    doc = KnowledgeDocument(
        company_id="comp_a",
        title="API 规范",
        content="RESTful API 设计规范",
    )

    async with aiosqlite.connect(db_path) as conn:
        created = await svc.create_document(conn, doc)
        assert created.document_id
        assert created.version == 1
        assert created.checksum

        fetched = await svc.get_document(conn, created.document_id, "comp_a")
        assert fetched is not None
        assert fetched.title == "API 规范"


async def test_update_document_cas(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "knowledge.db")
    await _setup_db(db_path)

    svc = KnowledgeService()
    doc = KnowledgeDocument(company_id="comp_a", title="v1", content="content v1")

    async with aiosqlite.connect(db_path) as conn:
        created = await svc.create_document(conn, doc)

        updated = await svc.update_document(conn, created, expected_version=1)
        assert updated.version == 2
        assert updated.content == "content v1"

        with pytest.raises(ValueError, match="version conflict"):
            await svc.update_document(conn, created, expected_version=1)


async def test_update_document_not_found(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "knowledge.db")
    await _setup_db(db_path)

    svc = KnowledgeService()
    doc = KnowledgeDocument(
        document_id="nonexistent", company_id="comp_a", title="x", content="y"
    )

    async with aiosqlite.connect(db_path) as conn:
        with pytest.raises(ValueError, match="document not found"):
            await svc.update_document(conn, doc, expected_version=1)


async def test_soft_delete_document(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "knowledge.db")
    await _setup_db(db_path)

    svc = KnowledgeService()
    doc = KnowledgeDocument(company_id="comp_a", title="t", content="c")

    async with aiosqlite.connect(db_path) as conn:
        created = await svc.create_document(conn, doc)
        await svc.delete_document(conn, created.document_id, "comp_a")

        fetched = await svc.get_document(conn, created.document_id, "comp_a")
        assert fetched is None


async def test_search_documents(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "knowledge.db")
    await _setup_db(db_path)

    svc = KnowledgeService()
    async with aiosqlite.connect(db_path) as conn:
        await svc.create_document(
            conn,
            KnowledgeDocument(
                company_id="comp_a", title="Python 指南", content="Python 最佳实践"
            ),
        )
        await svc.create_document(
            conn,
            KnowledgeDocument(
                company_id="comp_a",
                title="Go 指南",
                content="Go 最佳实践",
                source_category="official",
            ),
        )
        await svc.create_document(
            conn,
            KnowledgeDocument(
                company_id="comp_b", title="Python 内部", content="内部 Python 文档"
            ),
        )

        results = await svc.search(conn, "comp_a", "Python")
        assert len(results) == 1
        assert results[0].title == "Python 指南"

        results = await svc.search(conn, "comp_a", "指南")
        assert len(results) == 2

        results = await svc.search(
            conn, "comp_a", "指南", category="official"
        )
        assert len(results) == 1
        assert results[0].source_category == "official"


async def test_list_documents(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "knowledge.db")
    await _setup_db(db_path)

    svc = KnowledgeService()
    async with aiosqlite.connect(db_path) as conn:
        await svc.create_document(
            conn,
            KnowledgeDocument(company_id="comp_a", title="a", content="1"),
        )
        await svc.create_document(
            conn,
            KnowledgeDocument(
                company_id="comp_a", title="b", content="2", source_category="official"
            ),
        )

        all_docs = await svc.list_documents(conn, "comp_a")
        assert len(all_docs) == 2

        official = await svc.list_documents(conn, "comp_a", category="official")
        assert len(official) == 1
        assert official[0].source_category == "official"


async def test_version_increment(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "knowledge.db")
    await _setup_db(db_path)

    svc = KnowledgeService()
    doc = KnowledgeDocument(company_id="comp_a", title="t", content="v1")

    async with aiosqlite.connect(db_path) as conn:
        created = await svc.create_document(conn, doc)

        for i, content in enumerate(["v2", "v3", "v4"], start=2):
            updated = await svc.update_document(conn, created, expected_version=i - 1)
            assert updated.version == i
            created.content = content
            created.version = i

        fetched = await svc.get_document(conn, created.document_id, "comp_a")
        assert fetched is not None
        assert fetched.version == 4


async def test_embedding_service_embed_text() -> None:
    svc = EmbeddingService()
    vec = await svc.embed_text("hello world")
    assert isinstance(vec, list)
    assert len(vec) > 0
    assert all(isinstance(v, float) for v in vec)


async def test_embedding_service_embed_document() -> None:
    svc = EmbeddingService()
    doc = KnowledgeDocument(content="a" * 1200)
    count = await svc.embed_document(doc)
    assert count == 3

    empty_doc = KnowledgeDocument(content="")
    count = await svc.embed_document(empty_doc)
    assert count == 0
