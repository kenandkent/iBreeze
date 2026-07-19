"""向量存储抽象与 LanceDB 实现（Phase 8 P8-T3）。

设计 §9.5：VectorStore 抽象独立于具体向量库，便于替换。
LanceDB 0.34 已验证支持 pre-filter（search().where(..., prefilter=True) 在计算
相似度之前应用过滤条件），满足"ACL 下推到查询条件、先查全部再过滤"红线要求。

每个操作使用独立 LanceDB 连接，避免连接级快照缓存导致读旧数据。
"""

from __future__ import annotations

import asyncio
import os
import re
from abc import ABC, abstractmethod
from typing import Any

import lancedb


def _sanitize(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]", "_", name)


class VectorStore(ABC):
    """向量存储抽象。"""

    @abstractmethod
    async def upsert(
        self,
        chunk_id: str,
        company_id: str,
        generation_id: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None: ...

    @abstractmethod
    async def search(
        self,
        query_vec: list[float],
        prefilter: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """向量检索，prefilter 在 ANN 之前应用（pre-filter）。"""

    @abstractmethod
    async def delete_by_chunk(self, chunk_id: str) -> None: ...

    @abstractmethod
    async def delete_by_filter(self, where: str) -> None: ...

    @abstractmethod
    async def list_chunk_ids(self, where: str) -> list[str]: ...


class LanceVectorStore(VectorStore):
    """LanceDB 向量存储实现。

    每个公司一张表 `kg_vectors_<company_id>`，向量连同 company_id / generation_id /
    visibility 分支列一起存储。检索时通过 `where(prefilter=True)` 把 ACL 谓词下推到
    向量扫描之前，绝不在应用层召回后再过滤。
    """

    VECTOR_COLUMN = "vector"

    def __init__(self, db_path: str, dim: int) -> None:
        self._db_path = db_path
        self._dim = dim
        self._lance_dir = os.path.join(
            os.path.dirname(db_path) or ".",
            ".lancedb_" + os.path.basename(db_path).replace(".", "_"),
        )
        os.makedirs(self._lance_dir, exist_ok=True)

    def _fresh(self):
        return lancedb.connect(self._lance_dir)

    def _table_name(self, company_id: str) -> str:
        return "kg_vectors_" + _sanitize(company_id)

    def _open(self, conn, company_id: str):
        try:
            return conn.open_table(self._table_name(company_id))
        except Exception:
            return None

    def _run(self, fn):
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(None, fn)

    async def upsert(
        self,
        chunk_id: str,
        company_id: str,
        generation_id: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        vec = [float(x) for x in vector]
        row = {
            "chunk_id": chunk_id,
            "company_id": company_id,
            "generation_id": generation_id,
            "visibility": metadata.get("visibility", "company"),
            "department_id": metadata.get("department_id") or "",
            "task_id": metadata.get("task_id") or "",
            "employee_id": metadata.get("employee_id") or "",
            "document_id": metadata.get("document_id", ""),
            "text": metadata.get("text", ""),
            self.VECTOR_COLUMN: vec,
        }

        def _do() -> None:
            conn = self._fresh()
            tbl = self._open(conn, company_id)
            if tbl is None:
                conn.create_table(self._table_name(company_id), data=[row])
                return
            try:
                tbl.delete(f"chunk_id = '{chunk_id}'")
            except Exception:
                pass
            tbl.add([row])

        await self._run(_do)

    async def search(
        self,
        query_vec: list[float],
        prefilter: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        q = [float(x) for x in query_vec]

        def _do() -> list[dict[str, Any]]:
            company = self._company_from_where(prefilter)
            if company is None:
                return []
            conn = self._fresh()
            tbl = self._open(conn, company)
            if tbl is None:
                return []
            rs = (
                tbl.search(q, vector_column_name=self.VECTOR_COLUMN)
                .where(prefilter, prefilter=True)
                .limit(limit)
                .to_list()
            )
            return [
                {
                    "chunk_id": r["chunk_id"],
                    "document_id": r.get("document_id", ""),
                    "score": float(r.get("_distance", 0.0)),
                    "visibility": r.get("visibility", "company"),
                    "department_id": r.get("department_id", ""),
                    "task_id": r.get("task_id", ""),
                    "employee_id": r.get("employee_id", ""),
                    "text": r.get("text", ""),
                }
                for r in rs
            ]

        return await self._run(_do)

    async def delete_by_chunk(self, chunk_id: str) -> None:
        def _do() -> None:
            conn = self._fresh()
            for _name in conn.table_names():
                name = _name
                if not name.startswith("kg_vectors_"):
                    continue
                try:
                    conn.open_table(name).delete(f"chunk_id = '{chunk_id}'")
                except Exception:
                    pass

        await self._run(_do)

    async def delete_by_filter(self, where: str) -> None:
        company = self._company_from_where(where)

        def _do() -> None:
            conn = self._fresh()
            if company is None:
                for _name in conn.table_names():
                    name = _name
                    if name.startswith("kg_vectors_"):
                        try:
                            conn.open_table(name).delete(where)
                        except Exception:
                            pass
                return
            tbl = self._open(conn, company)
            if tbl is not None:
                tbl.delete(where)

        await self._run(_do)

    async def list_chunk_ids(self, where: str) -> list[str]:
        company = self._company_from_where(where)

        def _do() -> list[str]:
            conn = self._fresh()
            if company is not None:
                names = [self._table_name(company)]
            else:
                names = [
                    n for n in conn.table_names() if n.startswith("kg_vectors_")
                ]
            out: list[str] = []
            for name in names:
                tbl = self._open(conn, company) if company else self._try_open(conn, name)
                if tbl is None:
                    continue
                try:
                    arrow = tbl.to_arrow()
                    rows = arrow.to_pylist()
                except Exception:
                    rows = []
                for r in rows:
                    if self._matches(r, where):
                        out.append(r["chunk_id"])
            return out

        return await self._run(_do)

    def _try_open(self, conn, name: str):
        try:
            return conn.open_table(name)
        except Exception:
            return None

    @staticmethod
    def _company_from_where(where: str) -> str | None:
        m = re.search(r"company_id\s*=\s*'([^']+)'", where)
        return m.group(1) if m else None

    @staticmethod
    def _matches(row: dict, where: str) -> bool:
        conds = re.findall(r"(\w+)\s*=\s*'([^']*)'", where)
        for col, val in conds:
            if row.get(col) != val:
                return False
        return True

    def close(self) -> None:
        pass
