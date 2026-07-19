"""P8-T5 双写一致性对账测试：SQLite/LanceDB 缺失补齐与孤儿清理。"""

from __future__ import annotations

import aiosqlite
import pytest

from tests.knowledge._helpers import seed_company, setup_db
from acos.knowledge.embedding import LocalEmbedding
from acos.knowledge.reconciler import Reconciler
from acos.knowledge.vector_store import LanceVectorStore


async def _seed_chunk(db_path, chunk_id, company_id, doc_id, content, gen):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO knowledge_chunks
                  (chunk_id, document_id, company_id, content, chunk_index, embedding_status,
                   source_record_id, visibility, vector_status)
               VALUES (?, ?, ?, ?, 0, 'pending', 'sr', 'company', 'pending')""",
            (chunk_id, doc_id, company_id, content),
        )
        await db.commit()


@pytest.fixture
async def env(tmp_path):
    db_path = await setup_db(tmp_path)
    await seed_company(db_path, "comp_a")
    emb = LocalEmbedding()
    vs = LanceVectorStore(db_path, emb.dim)
    gen = "g1"
    yield db_path, emb, vs, gen
    vs.close()


async def test_reconcile_embeds_missing(env) -> None:
    db_path, emb, vs, gen = env
    await _seed_chunk(db_path, "c1", "comp_a", "d1", "缺失向量的内容", gen)
    rec = Reconciler(db_path, emb, vs)
    report = await rec.reconcile("comp_a", gen)
    assert report["missing_embedded"] == 1
    ids = await vs.list_chunk_ids(f"company_id = 'comp_a' AND generation_id = '{gen}'")
    assert "c1" in ids


async def test_reconcile_cleans_orphan(env) -> None:
    db_path, emb, vs, gen = env
    # LanceDB 有孤儿向量，SQLite 无对应 chunk
    vec = await emb.embed_text("孤儿内容")
    await vs.upsert("orphan", "comp_a", gen, vec,
                   {"visibility": "company", "document_id": "dx", "text": "孤儿内容"})
    rec = Reconciler(db_path, emb, vs)
    report = await rec.reconcile("comp_a", gen)
    assert report["orphan_cleaned"] == 1
    ids = await vs.list_chunk_ids(f"company_id = 'comp_a' AND generation_id = '{gen}'")
    assert "orphan" not in ids


async def test_reconcile_noop_when_consistent(env) -> None:
    db_path, emb, vs, gen = env
    await _seed_chunk(db_path, "c1", "comp_a", "d1", "一致内容", gen)
    vec = await emb.embed_text("一致内容")
    await vs.upsert("c1", "comp_a", gen, vec,
                   {"visibility": "company", "document_id": "d1", "text": "一致内容"})
    rec = Reconciler(db_path, emb, vs)
    report = await rec.reconcile("comp_a", gen)
    assert report["missing_embedded"] == 0
    assert report["orphan_cleaned"] == 0
