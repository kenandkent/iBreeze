"""SQLite / LanceDB 双写一致性对账（Phase 8 P8-T5）。

设计 §9.5：知识元数据（SQLite）与向量（LanceDB）是两个独立存储，写入非原子，
需后台对账兜底。后台 Worker 定期比对 knowledge_chunks 期望状态与 LanceDB 实际内容：
- SQLite 有记录但 LanceDB 缺向量 → 重新嵌入补齐
- LanceDB 有向量但 SQLite 无对应记录（孤儿）→ 删除
"""

from __future__ import annotations

import aiosqlite

from acos.knowledge.embedding import LocalEmbedding
from acos.knowledge.vector_store import VectorStore


class Reconciler:
    """双写一致性对账 Worker。"""

    def __init__(
        self,
        db_path: str,
        embedding: LocalEmbedding,
        vector_store: VectorStore,
    ) -> None:
        self._db_path = db_path
        self._embedding = embedding
        self._vs = vector_store

    async def _conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def reconcile(self, company_id: str, generation_id: str) -> dict[str, int]:
        """对齐 SQLite chunks 与 LanceDB 向量，返回补齐/清理计数。"""
        conn = await self._conn()
        try:
            # 1) SQLite 期望集合
            cur = await conn.execute(
                """SELECT chunk_id, company_id, document_id, content, visibility,
                          department_id, task_id, employee_id, source_record_id
                   FROM knowledge_chunks
                   WHERE company_id = ? AND deleted_at IS NULL""",
                (company_id,),
            )
            chunks = [dict(r) for r in await cur.fetchall()]
        finally:
            await conn.close()

        expected_ids = {c["chunk_id"] for c in chunks}
        expected_map = {c["chunk_id"]: c for c in chunks}

        # 2) LanceDB 实际集合
        actual_ids = set(
            await self._vs.list_chunk_ids(
                f"company_id = '{company_id}' AND generation_id = '{generation_id}'"
            )
        )

        missing = expected_ids - actual_ids
        orphan = actual_ids - expected_ids

        # 3) 补齐缺失向量
        embedded = 0
        for cid in missing:
            c = expected_map[cid]
            vec = await self._embedding.embed_text(c["content"])
            await self._vs.upsert(
                cid, company_id, generation_id, vec,
                {
                    "visibility": c["visibility"],
                    "department_id": c["department_id"],
                    "task_id": c["task_id"],
                    "employee_id": c["employee_id"],
                    "document_id": c["document_id"],
                    "text": c["content"],
                },
            )
            embedded += 1

        # 4) 清理孤儿向量
        cleaned = 0
        for cid in orphan:
            await self._vs.delete_by_chunk(cid)
            cleaned += 1

        return {
            "missing_embedded": embedded,
            "orphan_cleaned": cleaned,
            "expected": len(expected_ids),
            "actual": len(actual_ids),
        }

    async def delete_orphan_vectors(self, company_id: str) -> int:
        """仅清理孤儿（测试用）。"""
        conn = await self._conn()
        try:
            cur = await conn.execute(
                "SELECT chunk_id FROM knowledge_chunks WHERE company_id = ?",
                (company_id,),
            )
            valid = {r["chunk_id"] for r in await cur.fetchall()}
        finally:
            await conn.close()
        actual = set(await self._vs.list_chunk_ids(f"company_id = '{company_id}'"))
        orphan = actual - valid
        for cid in orphan:
            await self._vs.delete_by_chunk(cid)
        return len(orphan)
