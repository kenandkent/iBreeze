"""知识库写操作 RPC 方法集合。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from acos.knowledge.models import KnowledgeDocument
from acos.knowledge.service import KnowledgeService
from acos.rpc.server import RPCServer


class KnowledgeMethods:
    """知识库相关的 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._svc = KnowledgeService()

    def register_to(self, server: RPCServer) -> None:
        server.register_method("knowledge.update", self._knowledge_update)
        server.register_method("knowledge.delete", self._knowledge_delete)
        server.register_method("knowledge.search", self._knowledge_search)

    async def _get_conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def _knowledge_update(self, params: dict[str, Any]) -> dict[str, Any]:
        document_id = params.get("document_id")
        company_id = params.get("company_id")
        expected_version = params.get("expected_version", 1)
        if not document_id or not company_id:
            return {"error": "missing document_id or company_id"}
        conn = await self._get_conn()
        try:
            doc = KnowledgeDocument(
                document_id=document_id,
                company_id=company_id,
                title=params.get("title", ""),
                content=params.get("content", ""),
                source_category=params.get("source_category", "custom"),
            )
            if "status" in params:
                doc.status = params["status"]
            doc = await self._svc.update_document(conn, doc, expected_version)
            return {"document_id": doc.document_id, "version": doc.version, "status": doc.status}
        except ValueError as e:
            return {"error": str(e)}
        finally:
            await conn.close()

    async def _knowledge_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        document_id = params.get("document_id")
        company_id = params.get("company_id")
        if not document_id or not company_id:
            return {"error": "missing document_id or company_id"}
        conn = await self._get_conn()
        try:
            await self._svc.delete_document(conn, document_id, company_id)
            return {"deleted": True}
        except ValueError as e:
            return {"error": str(e)}
        finally:
            await conn.close()

    async def _knowledge_search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        company_id = params.get("company_id")
        query = params.get("query", "")
        category = params.get("category")
        if not company_id:
            return {"error": "missing company_id"}
        conn = await self._get_conn()
        try:
            docs = await self._svc.search(conn, company_id, query, category)
            return [
                {
                    "document_id": d.document_id,
                    "company_id": d.company_id,
                    "title": d.title,
                    "source_category": d.source_category,
                    "status": d.status,
                }
                for d in docs
            ]
        finally:
            await conn.close()
