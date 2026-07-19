"""kg.* 命名空间 RPC 方法集合（Phase 8 P8-T4a）。

设计 §9.4 / 附录 B.5：kg.document.list/get、kg.citation.get、kg.search、
kg.source.delete、kg.knowledge.reject/confirm、kg.ingest.retry 等。

安全要点：
- actor 服务端注入 LocalOwner，不接受客户端 actor 参数
- 跨公司/越权拒绝
- confirm/reject 审计 operator=LocalOwner
- 检索路径委托 Retriever（ACL 下推到查询条件）
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import aiosqlite

from acos.knowledge.embedding import LocalEmbedding
from acos.knowledge.extractor import Extractor, PolicyService
from acos.knowledge.raw_store import RawStore
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
from acos.settings.service import SettingsService


class KgMethods:
    """kg.* 相关 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._svc = KnowledgeService()
        self._raw = RawStore()
        self._server: RPCServer | None = None
        self._embedding = LocalEmbedding()
        self._vs = LanceVectorStore(db_path, self._embedding.dim)
        self._perm = PermissionEngine(db_path)
        self._settings = SettingsService(db_path)
        self._retriever = Retriever(db_path, self._embedding, self._vs, self._perm)
        self._notifier = None

    def set_notifier(self, notifier) -> None:
        self._notifier = notifier

    def register_to(self, server: RPCServer) -> None:
        self._server = server
        server.register_method("kg.document.list", self._document_list)
        server.register_method("kg.document.get", self._document_get)
        server.register_method("kg.citation.get", self._citation_get)
        server.register_method("kg.search", self._search)
        server.register_method("kg.source.delete", self._source_delete)
        server.register_method("kg.knowledge.reject", self._knowledge_reject)
        server.register_method("kg.knowledge.confirm", self._knowledge_confirm)
        server.register_method("kg.ingest.retry", self._ingest_retry)
        server.register_method("kg.reindex", self._reindex)

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

    async def _write_gov_audit(
        self, conn, company_id, operator, action, target_type, target_id, reason=None, metadata=None
    ) -> None:
        # 表由 0003_audit_tables 建立（列 id/company_id/resource_type/resource_id/...
        # operator/reason/trace_id/timestamp），0048 补充 operator_type/target_type/
        # target_id/metadata。
        await conn.execute(
            """INSERT INTO knowledge_governance_audit
                  (id, company_id, operator, operator_type, action, resource_type,
                   resource_id, target_type, target_id, reason, metadata, trace_id)
               VALUES (?, ?, ?, 'local_owner', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid.uuid4().hex, company_id, operator, action,
                target_type, target_id, target_type, target_id, reason,
                json.dumps(metadata or {}), uuid.uuid4().hex,
            ),
        )
        await conn.commit()

    # ── 浏览 ────────────────────────────────────────────

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

    # ── 治理命令 ────────────────────────────────────────

    async def _source_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        source_type = params.get("source_type")
        source_id = params.get("source_id")
        mode = params.get("mode", "soft")
        if not company_id or not source_type or not source_id:
            return {"error": "missing required params"}
        conn = await self._conn()
        try:
            owner = await self._require_owner(conn)
            cur = await conn.execute(
                """SELECT source_record_id, status FROM knowledge_sources
                   WHERE company_id = ? AND source_type = ? AND source_id = ? LIMIT 1""",
                (company_id, source_type, source_id),
            )
            row = await cur.fetchone()
            if row is None:
                return {"error": "KG-NOT-FOUND"}
            src_rec = row["source_record_id"]

            if mode == "hard":
                cur = await conn.execute(
                    "SELECT document_id FROM knowledge_documents WHERE source_record_id = ?",
                    (src_rec,),
                )
                doc_ids = [r["document_id"] for r in await cur.fetchall()]
                for did in doc_ids:
                    cur = await conn.execute(
                        "SELECT chunk_id FROM knowledge_chunks WHERE document_id = ?", (did,)
                    )
                    for cr in await cur.fetchall():
                        await self._vs.delete_by_chunk(cr["chunk_id"])
                await conn.execute(
                    "DELETE FROM knowledge_citations WHERE source_record_id = ?", (src_rec,)
                )
                await conn.execute(
                    "DELETE FROM knowledge_chunks WHERE source_record_id = ?", (src_rec,)
                )
                await conn.execute(
                    "DELETE FROM knowledge_documents WHERE source_record_id = ?", (src_rec,)
                )
            else:
                await conn.execute(
                    "UPDATE knowledge_documents SET status = 'deleted',"
                    " deleted_at = datetime('now') WHERE source_record_id = ?",
                    (src_rec,),
                )
                await conn.execute(
                    "UPDATE knowledge_citations SET status = 'source_deleted'"
                    " WHERE source_record_id = ?",
                    (src_rec,),
                )

            await conn.execute(
                "UPDATE knowledge_sources SET status = 'deleted', updated_at = datetime('now') "
                "WHERE source_record_id = ?", (src_rec,)
            )
            await self._write_gov_audit(
                conn, company_id, owner, "source_delete", "knowledge_source",
                src_rec, reason=mode, metadata={"mode": mode},
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"ok": True, "mode": mode, "source_record_id": src_rec}

    async def _knowledge_reject(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        knowledge_id = params.get("knowledge_id")
        reason = params.get("reason")
        if not company_id or not knowledge_id:
            return {"error": "missing required params"}
        conn = await self._conn()
        try:
            owner = await self._require_owner(conn)
            cur = await conn.execute(
                "SELECT 1 FROM knowledge_documents WHERE document_id = ? AND company_id = ?",
                (knowledge_id, company_id),
            )
            if (await cur.fetchone()) is None:
                return {"error": "KG-NOT-FOUND"}
            await conn.execute(
                "UPDATE knowledge_documents SET status = 'rejected', updated_at = datetime('now') "
                "WHERE document_id = ? AND company_id = ?",
                (knowledge_id, company_id),
            )
            await conn.execute("DELETE FROM knowledge_fts WHERE document_id = ?", (knowledge_id,))
            await self._write_gov_audit(
                conn, company_id, owner, "knowledge_reject", "knowledge",
                knowledge_id, reason=reason,
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"ok": True, "status": "rejected"}

    async def _knowledge_confirm(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        knowledge_id = params.get("knowledge_id")
        if not company_id or not knowledge_id:
            return {"error": "missing required params"}
        conn = await self._conn()
        try:
            owner = await self._require_owner(conn)
            cur = await conn.execute(
                "SELECT 1 FROM knowledge_documents WHERE document_id = ? AND company_id = ?",
                (knowledge_id, company_id),
            )
            if (await cur.fetchone()) is None:
                return {"error": "KG-NOT-FOUND"}
            await conn.execute(
                "UPDATE knowledge_documents SET governance_confirmed = 1,"
                " updated_at = datetime('now') WHERE document_id = ? AND company_id = ?",
                (knowledge_id, company_id),
            )
            await self._write_gov_audit(
                conn, company_id, owner, "knowledge_confirm", "knowledge",
                knowledge_id, reason="LocalOwner 治理确认",
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"ok": True, "governance_confirmed": True}

    async def _ingest_retry(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        job_id = params.get("job_id")
        if not company_id or not job_id:
            return {"error": "missing required params"}
        conn = await self._conn()
        try:
            owner = await self._require_owner(conn)
            cur = await conn.execute(
                """SELECT company_id, source_record_id, status
                   FROM knowledge_ingestion_jobs WHERE job_id = ?""",
                (job_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return {"error": "KG-EXTRACT-FAILED"}
            if row["company_id"] != company_id:
                return {"error": ORG_PERM_DENIED}
            if row["status"] not in ("retryable", "failed"):
                return {"error": "KG-EXTRACT-FAILED", "detail": "job 不可重试"}
            raw_text = await self._load_raw_text(conn, row["source_record_id"])
            resolved = await PolicyService(self._settings).resolve(company_id)
            extractor = Extractor(
                _FakeProviderFactory(), PolicyService(self._settings),
                notifier=self._notifier, embedding=self._embedding,
            )
            new_job = await extractor.retry_job(
                conn, job_id, resolved, raw_text, "custom"
            )
            await self._write_gov_audit(
                conn, company_id, owner, "ingest_retry", "ingestion_job",
                job_id, metadata={"new_job_id": new_job},
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"ok": True, "new_job_id": new_job}

    async def _load_raw_text(self, conn, source_record_id: str) -> str:
        cur = await conn.execute(
            "SELECT content FROM knowledge_documents WHERE source_record_id = ? LIMIT 1",
            (source_record_id,),
        )
        row = await cur.fetchone()
        return row["content"] if row else ""

    # ── ACL 辅助 ────────────────────────────────────────

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

    async def _reindex(self, params: dict[str, Any]) -> dict[str, Any]:
        """kg.reindex：重建指定公司（及可选 source）全部 chunk 的向量索引。

        真实重嵌入：读取 chunks → 本地 embedding → upsert 到 LanceDB（带 generation_id
        与 ACL 分支 metadata 供 pre-filter）→ 标记 embedding_status='indexed'。
        """
        company_id = params.get("company_id")
        if not company_id:
            raise create_error(ORG_PERM_DENIED, "company_id 必填")
        source_id = params.get("source_id")
        generation_id = params.get("generation_id") or "reindex"

        conn = await self._conn()
        if source_id:
            cursor = await conn.execute(
                """SELECT c.chunk_id, c.document_id, c.company_id, c.content,
                          c.chunk_index, c.visibility, c.department_id, c.task_id, c.employee_id
                   FROM knowledge_chunks c
                   JOIN knowledge_documents d ON d.document_id = c.document_id
                   WHERE c.company_id = ? AND d.source_id = ?""",
                (company_id, source_id),
            )
        else:
            cursor = await conn.execute(
                """SELECT chunk_id, document_id, company_id, content, chunk_index,
                          visibility, department_id, task_id, employee_id
                   FROM knowledge_chunks WHERE company_id = ?""",
                (company_id,),
            )
        rows = await cursor.fetchall()

        if not rows:
            return {"reindexed": 0, "company_id": company_id, "generation_id": generation_id}

        texts = [r["content"] for r in rows]
        vectors = await self._embedding.embed(texts)

        for row, vec in zip(rows, vectors):
            metadata = {
                "visibility": row["visibility"],
                "department_id": row["department_id"],
                "task_id": row["task_id"],
                "employee_id": row["employee_id"],
            }
            await self._vs.upsert(
                chunk_id=row["chunk_id"],
                company_id=row["company_id"],
                generation_id=generation_id,
                vector=vec,
                metadata=metadata,
            )

        chunk_ids = [r["chunk_id"] for r in rows]
        conn = await self._conn()
        for cid in chunk_ids:
            await conn.execute(
                "UPDATE knowledge_chunks SET embedding_status = 'indexed' WHERE chunk_id = ?",
                (cid,),
            )
        await conn.commit()

        return {
            "reindexed": len(rows),
            "company_id": company_id,
            "generation_id": generation_id,
        }


class _FakeProviderFactory:
    """默认 Provider 工厂：返回 FakeProviderAdapter（无需真实网络）。"""

    async def create(self, resolved):
        from acos.providers.fake import FakeProviderAdapter

        return FakeProviderAdapter(provider_id=resolved.provider, models=[resolved.model])
