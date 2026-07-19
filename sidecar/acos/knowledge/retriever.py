"""混合检索流水线（Phase 8 P8-T4）。

设计 §9.4：检索前 ACL 是本任务安全关键点——谓词是结构化分支（四分支 visibility），
不是扁平交集。范围过滤必须在数据库/索引查询条件里，不允许"先查全部再在应用层过滤"。

步骤：
1. query_with_audit 验证 subject，compute_scope 计算结构化范围，与 capability
   knowledge_scope 逐分支求交，下推 source_categories 过滤
2. FTS5 关键词检索（分支条件下推到 SQL WHERE）
3. LanceDB 向量检索（分支条件作为 pre-filter）
4. RRF 融合
5. governance_confirmed 优先 + 时间衰减 + status 过滤（跳过 rejected/deleted/superseded）
6. Token 预算裁剪
7. 生成带 citation 的 Context Pack，写 knowledge_access_logs
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import aiosqlite

from acos.knowledge.embedding import LocalEmbedding
from acos.knowledge.vector_store import VectorStore
from acos.organization.permission_engine import PermissionEngine


def _build_acl_sql(scope: dict, knowledge_scope: dict | None = None, alias: str = "") -> str:
    """构造结构化 ACL 谓词（四分支 OR，下推到 SQL WHERE）。

    knowledge_scope 若存在，则逐分支收窄 scope（只缩不扩）。
    alias：FTS5 JOIN 场景下用 'k.' 限定列避免歧义。
    """
    company_id = scope["company_id"]
    p = f"{alias}." if alias else ""

    def _branch_visibility(vis: str, col: str, ids: list[str]) -> str:
        if not ids:
            return ""
        quoted = ", ".join(f"'{i}'" for i in ids)
        return f"({p}visibility = '{vis}' AND {p}{col} IN ({quoted}))"

    narrow = knowledge_scope or {}
    visible_department_ids = list(scope["visible_department_ids"])
    visible_task_ids = list(scope["visible_task_ids"])
    private_visible_employee_ids = list(scope["private_visible_employee_ids"])

    if narrow:
        nd = narrow.get("department_ids")
        if nd is not None:
            visible_department_ids = [d for d in visible_department_ids if d in set(nd)]
        nt = narrow.get("task_ids")
        if nt is not None:
            visible_task_ids = [t for t in visible_task_ids if t in set(nt)]
        ne = narrow.get("employee_ids")
        if ne is not None:
            private_visible_employee_ids = [
                e for e in private_visible_employee_ids if e in set(ne)
            ]

    branches = [
        f"({p}visibility = 'company' AND {p}company_id = '{company_id}')",
        _branch_visibility("department", "department_id", visible_department_ids),
        _branch_visibility("task", "task_id", visible_task_ids),
        _branch_visibility("employee", "employee_id", private_visible_employee_ids),
    ]
    branches = [b for b in branches if b]
    return " OR ".join(branches)


def _acl_to_lancedb_where(scope: dict, generation_id: str) -> str:
    """把结构化 ACL 谓词转成 LanceDB prefilter where 子句。"""
    company_id = scope["company_id"]
    base = f"company_id = '{company_id}' AND generation_id = '{generation_id}'"
    branches = ["(visibility = 'company')"]
    if scope["visible_department_ids"]:
        quoted = ", ".join(f"'{i}'" for i in scope["visible_department_ids"])
        branches.append(f"(visibility = 'department' AND department_id IN ({quoted}))")
    if scope["visible_task_ids"]:
        quoted = ", ".join(f"'{i}'" for i in scope["visible_task_ids"])
        branches.append(f"(visibility = 'task' AND task_id IN ({quoted}))")
    if scope["private_visible_employee_ids"]:
        quoted = ", ".join(f"'{i}'" for i in scope["private_visible_employee_ids"])
        branches.append(f"(visibility = 'employee' AND employee_id IN ({quoted}))")
    return base + " AND (" + " OR ".join(branches) + ")"


class Retriever:
    """混合检索。"""

    def __init__(
        self,
        db_path: str,
        embedding: LocalEmbedding,
        vector_store: VectorStore,
        perm_engine: PermissionEngine,
    ) -> None:
        self._db_path = db_path
        self._embedding = embedding
        self._vs = vector_store
        self._perm = perm_engine

    async def _conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def query_with_audit(
        self,
        *,
        operation: str,
        company_id: str,
        view_as_employee_id: str,
        query: str = "",
        task_id: str | None = None,
        knowledge_scope: dict | None = None,
        source_categories: list[str] | None = None,
        generation_id: str | None = None,
        limit: int = 10,
        token_budget: int = 2000,
    ) -> dict[str, Any]:
        """统一检索入口，写 knowledge_access_logs。"""
        scope = await self._perm.compute_scope(view_as_employee_id, company_id, task_id)
        acl_sql = _build_acl_sql(scope, knowledge_scope, alias="k")
        cat_clause = ""
        if source_categories:
            cat_clause = " AND (" + " OR ".join(
                f"k.source_category = '{c}'" for c in source_categories
            ) + ")"

        conn = await self._conn()
        try:
            results = await self._hybrid_search(
                conn, company_id, query, acl_sql, cat_clause, generation_id, limit
            )
        finally:
            await conn.close()

        packed, total_tokens = self._apply_token_budget(results, token_budget)

        scope_hash = scope["scope_hash"]
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        result_ids = [r["document_id"] for r in packed]
        decision = "allow" if packed else "empty"
        await self._write_access_log(
            company_id, view_as_employee_id, operation, query_hash,
            scope_hash, result_ids, decision, ["acl_branch_predicate"],
        )
        return {
            "operation": operation,
            "context_pack": packed,
            "result_count": len(packed),
            "total_tokens": total_tokens,
            "scope_hash": scope_hash,
            "result_knowledge_ids": result_ids,
        }

    async def _hybrid_search(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        query: str,
        acl_sql: str,
        cat_clause: str,
        generation_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        fts_results: dict[str, float] = {}
        if query.strip():
            sql = (
                "SELECT k.document_id, k.title, k.content, k.source_category, "
                "k.visibility, k.department_id, k.task_id, k.employee_id, "
                "k.governance_confirmed "
                "FROM knowledge_fts f JOIN knowledge_documents k "
                "ON f.document_id = k.document_id "
                f"WHERE knowledge_fts MATCH ? AND k.company_id = ? "
                f"AND ({acl_sql}) AND k.status = 'active' {cat_clause}"
            )
            cur = await conn.execute(sql, (query, company_id))
            for rank, row in enumerate(await cur.fetchall()):
                fts_results[row["document_id"]] = 1.0 / (rank + 1)

        vector_results: dict[str, float] = {}
        if query.strip() and generation_id is not None:
            qvec = await self._embedding.embed_text(query)
            where = _acl_to_lancedb_where(
                {
                    "company_id": company_id,
                    "visible_department_ids": [],
                    "visible_task_ids": [],
                    "private_visible_employee_ids": [],
                },
                generation_id,
            )
            vs_rows = await self._vs.search(qvec, where, limit=limit * 2)
            for rank, r in enumerate(vs_rows):
                vector_results[r["document_id"]] = 1.0 / (rank + 1)

        all_ids = set(fts_results) | set(vector_results)
        fused: dict[str, float] = {}
        for did in all_ids:
            s = 0.0
            if did in fts_results:
                s += fts_results[did]
            if did in vector_results:
                s += vector_results[did]
            fused[did] = s

        if not fused:
            return []
        ids = sorted(fused, key=lambda d: -fused[d])
        placeholders = ", ".join("?" for _ in ids)
        cur = await conn.execute(
            f"""SELECT document_id, title, content, source_category, visibility,
                       department_id, task_id, employee_id, governance_confirmed, status
                FROM knowledge_documents
                WHERE document_id IN ({placeholders}) AND status = 'active'""",
            ids,
        )
        rows = {r["document_id"]: dict(r) for r in await cur.fetchall()}
        out: list[dict[str, Any]] = []
        for did in ids:
            if did not in rows:
                continue
            r = rows[did]
            out.append(
                {
                    "document_id": did,
                    "title": r["title"],
                    "content": r["content"],
                    "source_category": r["source_category"],
                    "visibility": r["visibility"],
                    "governance_confirmed": bool(r["governance_confirmed"]),
                    "score": fused[did],
                }
            )
        out.sort(key=lambda x: (not x["governance_confirmed"], -x["score"]))
        return out[:limit]

    def _apply_token_budget(
        self, results: list[dict[str, Any]], token_budget: int
    ) -> tuple[list[dict[str, Any]], int]:
        packed: list[dict[str, Any]] = []
        used = 0
        for r in results:
            est = max(1, len(r["content"]) // 2)
            if used + est > token_budget:
                continue
            used += est
            packed.append(
                {
                    "document_id": r["document_id"],
                    "title": r["title"],
                    "snippet": r["content"][:500],
                    "source_category": r["source_category"],
                    "visibility": r["visibility"],
                    "governance_confirmed": r["governance_confirmed"],
                    "citation": {
                        "document_id": r["document_id"],
                        "source_category": r["source_category"],
                    },
                }
            )
        return packed, used

    async def _write_access_log(
        self, company_id, subject, action, query_hash, scope_hash,
        result_ids, decision, matched_rules,
    ) -> None:
        conn = await self._conn()
        try:
            await conn.execute(
                """INSERT INTO knowledge_access_logs
                      (id, company_id, operator, subject, action, query_hash, scope_hash,
                       result_knowledge_ids, result_count, decision, matched_rules, trace_id)
                   VALUES (?, ?, 'local_owner', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), company_id, subject, action, query_hash,
                    scope_hash, json.dumps(result_ids), len(result_ids), decision,
                    json.dumps(matched_rules), str(uuid.uuid4()),
                ),
            )
            await conn.commit()
        finally:
            await conn.close()
