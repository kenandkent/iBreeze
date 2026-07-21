"""kg.* 命名空间 RPC 方法集合（精简后仅保留 4 个浏览/检索方法）。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from acos.knowledge.embedding import LocalEmbedding
from acos.knowledge.retriever import Retriever
from acos.knowledge.service import KnowledgeService
from acos.knowledge.vector_store import LanceVectorStore
from acos.organization.permission_engine import PermissionEngine
from acos.organization.principal import get_local_owner
from acos.rpc.errors import (
    ORG_PERM_DENIED,
    create_error,
)
from acos.rpc.server import RPCServer


class KgMethods:
    """kg.* 相关 RPC 方法（仅 4 个浏览/检索方法）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._svc = KnowledgeService()
        self._server: RPCServer | None = None
        self._embedding = LocalEmbedding()
        self._vs = LanceVectorStore(db_path, self._embedding.dim)
        self._perm = PermissionEngine(db_path)
        self._retriever = Retriever(db_path, self._embedding, self._vs, self._perm)

    def register_to(self, server: RPCServer) -> None:
        self._server = server
        server.register_method("kg.document.list", self._document_list)
        server.register_method("kg.document.get", self._document_get)
        server.register_method("kg.citation.get", self._citation_get)
        server.register_method("kg.search", self._search)

    async def _conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def _require_owner(self, conn: aiosqlite.Connection) -> str:
        owner = await get_local_owner(conn)
        return owner.owner_id

    async def _check_employee_company(
        self, conn: aiosqlite.Connection, employee_id: str, company_id: str
    ) -> bool:
        cur = await conn.execute(
            "SELECT 1 FROM employees WHERE employee_id = ? AND company_id = ?"
            " AND deleted_at IS NULL",
            (employee_id, company_id),
        )
        return (await cur.fetchone()) is not None

    def _scope_to_doc_filter(self, scope: dict) -> str:
        company_id = scope["company_id"]
        parts = [f"(visibility = 'company' AND company_id = '{company_id}')"]
        if scope["visible_department_ids"]:
            q = ", ".join(f"'{i}'" for i in scope["visible_department_ids"])
            parts.append(f"(visibility = 'department' AND department_id IN ({q}))")
        if scope["visible_task_ids"]:
            q = ", ".join(f"'{i}'" for i in scope["visible_task_ids"])
            parts.append(f"(visibility = 'task' AND task_id IN ({q}))")
        if scope["private_visible_employee_ids"]:
            q = ", ".join(f"'{i}'" for i in scope["private_visible_employee_ids"])
            parts.append(f"(visibility = 'employee' AND employee_id IN ({q}))")
        return " OR ".join(parts)

    def _allowed_by_scope(self, row, scope: dict) -> bool:
        vis = row["visibility"]
        if vis == "company":
            return row["company_id"] == scope["company_id"]
        if vis == "department":
            return row["department_id"] in scope["visible_department_ids"]
        if vis == "task":
            return row["task_id"] in scope["visible_task_ids"]
        if vis == "employee":
            return row["employee_id"] in scope["private_visible_employee_ids"]
        return False

    async def _document_list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        view_as = params.get("view_as_employee_id")
        if not company_id or not view_as:
            return {"error": "missing company_id or view_as_employee_id"}
        conn = await self._conn()
        try:
            if not await self._check_employee_company(conn, view_as, company_id):
                raise create_error(ORG_PERM_DENIED, "跨公司访问被拒绝")
            scope = await self._perm.compute_scope(view_as, company_id)
            acl = self._scope_to_doc_filter(scope)
            cat = params.get("source_category")
            sql = (
                "SELECT document_id, company_id, title, source_category, visibility, "
                "status, version, governance_confirmed FROM knowledge_documents "
                f"WHERE company_id = ? AND status = 'active' AND ({acl})"
            )
            args: list[Any] = [company_id]
            if cat:
                sql += " AND source_category = ?"
                args.append(cat)
            sql += " ORDER BY created_at DESC"
            cur = await conn.execute(sql, args)
            rows = await cur.fetchall()
        finally:
            await conn.close()
        return {
            "documents": [
                {
                    "document_id": r["document_id"],
                    "title": r["title"],
                    "source_category": r["source_category"],
                    "visibility": r["visibility"],
                    "governance_confirmed": bool(r["governance_confirmed"]),
                }
                for r in rows
            ]
        }

    async def _document_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        view_as = params.get("view_as_employee_id")
        knowledge_id = params.get("knowledge_id")
        if not company_id or not view_as or not knowledge_id:
            return {"error": "missing required params"}
        conn = await self._conn()
        try:
            if not await self._check_employee_company(conn, view_as, company_id):
                raise create_error(ORG_PERM_DENIED, "跨公司访问被拒绝")
            cur = await conn.execute(
                """SELECT document_id, company_id, title, content, source_category,
                          visibility, department_id, task_id, employee_id, status,
                          version, governance_confirmed
                   FROM knowledge_documents
                   WHERE document_id = ? AND company_id = ? AND status = 'active'""",
                (knowledge_id, company_id),
            )
            row = await cur.fetchone()
            if row is None:
                return {"error": "KG-NOT-FOUND"}
            scope = await self._perm.compute_scope(view_as, company_id)
            if not self._allowed_by_scope(row, scope):
                raise create_error(ORG_PERM_DENIED, "无权访问该知识")
        finally:
            await conn.close()
        return {
            "document_id": row["document_id"],
            "title": row["title"],
            "content": row["content"],
            "source_category": row["source_category"],
            "visibility": row["visibility"],
            "governance_confirmed": bool(row["governance_confirmed"]),
            "version": row["version"],
        }

    async def _citation_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        view_as = params.get("view_as_employee_id")
        citation_id = params.get("citation_id")
        if not company_id or not view_as or not citation_id:
            return {"error": "missing required params"}
        conn = await self._conn()
        try:
            if not await self._check_employee_company(conn, view_as, company_id):
                raise create_error(ORG_PERM_DENIED, "跨公司访问被拒绝")
            cur = await conn.execute(
                """SELECT c.citation_id, c.company_id, c.document_id, c.chunk_id,
                          c.source_record_id, c.locator, c.quote_hash, c.status,
                          d.visibility, d.department_id, d.task_id, d.employee_id
                   FROM knowledge_citations c
                   JOIN knowledge_documents d ON d.document_id = c.document_id
                   WHERE c.citation_id = ? AND c.company_id = ?""",
                (citation_id, company_id),
            )
            row = await cur.fetchone()
            if row is None:
                return {"error": "KG-NOT-FOUND"}
            scope = await self._perm.compute_scope(view_as, company_id)
            if not self._allowed_by_scope(row, scope):
                raise create_error(ORG_PERM_DENIED, "无权访问该引用")
            return {
                "citation_id": row["citation_id"],
                "document_id": row["document_id"],
                "chunk_id": row["chunk_id"],
                "source_record_id": row["source_record_id"],
                "locator": row["locator"],
                "quote_hash": row["quote_hash"],
                "status": row["status"],
            }
        finally:
            await conn.close()

    async def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        view_as = params.get("view_as_employee_id")
        if not company_id or not view_as:
            return {"error": "missing company_id or view_as_employee_id"}
        conn = await self._conn()
        try:
            if not await self._check_employee_company(conn, view_as, company_id):
                raise create_error(ORG_PERM_DENIED, "跨公司访问被拒绝")
        finally:
            await conn.close()
        generation_id = params.get("generation_id")
        result = await self._retriever.query_with_audit(
            operation="search",
            company_id=company_id,
            view_as_employee_id=view_as,
            query=params.get("query", ""),
            task_id=params.get("task_id"),
            knowledge_scope=params.get("knowledge_scope"),
            source_categories=params.get("source_categories"),
            generation_id=generation_id,
            limit=params.get("limit", 10),
        )
        return result
