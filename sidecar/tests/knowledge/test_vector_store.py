"""P8-T3 向量存储测试：LanceDB pre-filter 验证（安全红线核心）。"""

from __future__ import annotations

import pytest

from acos.knowledge.embedding import LocalEmbedding
from acos.knowledge.vector_store import LanceVectorStore


@pytest.fixture
def store(tmp_path):
    emb = LocalEmbedding()
    s = LanceVectorStore(str(tmp_path / "v.db"), emb.dim)
    yield s
    s.close()


async def test_prefilter_enforces_company_isolation(store) -> None:
    """跨公司向量不得出现在预过滤结果中（prefilter 在 ANN 之前应用）。"""
    v = [1.0, 0.0, 0.0] + [0.0] * (store._dim - 3)
    await store.upsert("a", "c1", "g1", v, {"visibility": "company", "document_id": "d_a"})
    await store.upsert("b", "c2", "g1", [0.0, 1.0, 0.0] + [0.0] * (store._dim - 3),
                      {"visibility": "company", "document_id": "d_b"})

    # 查询以 c1 的向量，预过滤只放行 c1
    res = await store.search(v, "company_id = 'c1' AND generation_id = 'g1' AND (visibility = 'company')", limit=10)
    ids = {r["chunk_id"] for r in res}
    assert "a" in ids
    assert "b" not in ids  # 零泄漏


async def test_prefilter_branch_visibility(store) -> None:
    """department 分支预过滤：仅放行可见部门。"""
    vec_dept = [1.0, 0.0, 0.0] + [0.0] * (store._dim - 3)
    await store.upsert("x", "c1", "g1", vec_dept,
                      {"visibility": "department", "department_id": "D1", "document_id": "dx"})
    await store.upsert("y", "c1", "g1", vec_dept,
                      {"visibility": "department", "department_id": "D2", "document_id": "dy"})
    q = [1.0, 0.0, 0.0] + [0.0] * (store._dim - 3)
    where = ("company_id = 'c1' AND generation_id = 'g1' AND "
             "((visibility = 'company') OR (visibility = 'department' AND department_id IN ('D1')))")
    res = await store.search(q, where, limit=10)
    ids = {r["chunk_id"] for r in res}
    assert "x" in ids
    assert "y" not in ids


async def test_delete_and_list_orphan(store) -> None:
    vec = [0.5] * store._dim
    await store.upsert("k1", "c1", "g1", vec, {"visibility": "company", "document_id": "d1"})
    ids = await store.list_chunk_ids("company_id = 'c1' AND generation_id = 'g1'")
    assert "k1" in ids
    await store.delete_by_chunk("k1")
    ids2 = await store.list_chunk_ids("company_id = 'c1' AND generation_id = 'g1'")
    assert "k1" not in ids2
