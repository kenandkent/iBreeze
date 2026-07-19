"""methods_knowledge RPC 方法单元测试。"""

import os
import tempfile

import aiosqlite
import pytest
from acos.rpc.methods_knowledge import KnowledgeMethods
from acos.store.migrator import Migrator

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "migrations")


@pytest.fixture
async def knowledge_methods() -> KnowledgeMethods:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        migrator = Migrator(db_path)
        await migrator.run_pending_migrations(MIGRATIONS_DIR)
        methods = KnowledgeMethods(db_path)
        yield methods
    finally:
        os.unlink(db_path)


async def _create_doc(methods: KnowledgeMethods, doc_id: str = "doc-001") -> None:
    conn = await aiosqlite.connect(methods._db_path)
    await conn.execute(
        """INSERT INTO knowledge_documents
           (document_id, company_id, title, content, source_type, source_path,
            source_category, visibility, embedding_status, checksum, version, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc_id, "comp-001", "Test Doc", "Hello world", "manual", None,
         "custom", "company", "done", "abc", 1, "active"),
    )
    await conn.commit()
    await conn.close()


class TestKnowledgeMethods:
    async def test_register(self, knowledge_methods: KnowledgeMethods) -> None:
        from acos.rpc.server import RPCServer
        server = RPCServer()
        knowledge_methods.register_to(server)
        assert "knowledge.update" in server._handlers
        assert "knowledge.delete" in server._handlers
        assert "knowledge.search" in server._handlers

    async def test_update_document(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_update({
            "document_id": "doc-001",
            "company_id": "comp-001",
            "expected_version": 1,
            "title": "Updated Title",
            "content": "Updated content",
        })
        assert result["document_id"] == "doc-001"
        assert result["version"] == 2

    async def test_update_missing_params(self, knowledge_methods: KnowledgeMethods) -> None:
        result = await knowledge_methods._knowledge_update({})
        assert "error" in result

    async def test_update_not_found(self, knowledge_methods: KnowledgeMethods) -> None:
        result = await knowledge_methods._knowledge_update({
            "document_id": "nonexistent",
            "company_id": "comp-001",
            "expected_version": 1,
            "title": "x",
            "content": "y",
        })
        assert "error" in result

    async def test_update_version_conflict(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_update({
            "document_id": "doc-001",
            "company_id": "comp-001",
            "expected_version": 99,
            "title": "x",
            "content": "y",
        })
        assert "error" in result

    async def test_delete_document(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_delete({
            "document_id": "doc-001",
            "company_id": "comp-001",
        })
        assert result["deleted"] is True

    async def test_delete_missing_params(self, knowledge_methods: KnowledgeMethods) -> None:
        result = await knowledge_methods._knowledge_delete({})
        assert "error" in result

    async def test_search_documents(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_search({
            "company_id": "comp-001",
            "query": "Hello",
        })
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "Test Doc"

    async def test_search_no_results(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_search({
            "company_id": "comp-001",
            "query": "nonexistent",
        })
        assert isinstance(result, list)
        assert len(result) == 0

    async def test_search_missing_company(self, knowledge_methods: KnowledgeMethods) -> None:
        result = await knowledge_methods._knowledge_search({"query": "x"})
        assert "error" in result

    async def test_update_with_status(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_update({
            "document_id": "doc-001",
            "company_id": "comp-001",
            "expected_version": 1,
            "title": "Updated",
            "content": "content",
            "status": "archived",
        })
        assert result["status"] == "archived"

    async def test_delete_value_error(self, knowledge_methods: KnowledgeMethods) -> None:
        result = await knowledge_methods._knowledge_delete({
            "document_id": "nonexistent",
            "company_id": "comp-001",
        })
        assert result == {"deleted": True}

    async def test_search_with_category(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_search({
            "company_id": "comp-001",
            "query": "Hello",
            "category": "custom",
        })
        assert isinstance(result, list)
        assert len(result) == 1

    async def test_search_wrong_category(self, knowledge_methods: KnowledgeMethods) -> None:
        await _create_doc(knowledge_methods)
        result = await knowledge_methods._knowledge_search({
            "company_id": "comp-001",
            "query": "Hello",
            "category": "policy",
        })
        assert isinstance(result, list)
        assert len(result) == 0
