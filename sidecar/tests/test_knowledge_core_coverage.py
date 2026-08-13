"""Coverage for knowledge core modules: vector_store, embeddings, hybrid_search, generation.

Closes gaps in the success paths: LanceDB table open/create, upsert/search/delete
happy paths, ONNX embedding inference, hybrid-search candidate whitelisting and
the knowledge access log write, and LanceDB row counting.
"""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ibreeze.knowledge.embeddings import EMBEDDING_DIM, EmbeddingService
from ibreeze.knowledge.generation import (
    count_lancedb_items,
    count_lancedb_items_for_generation,
)
from ibreeze.knowledge.hybrid_search import hybrid_search
from ibreeze.knowledge.vector_store import VectorStore


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


# ── vector_store ─────────────────────────────────────────────────────


class TestVectorStoreGetTableSuccess:
    def test_opens_existing_table(self):
        store = VectorStore(db_path="/tmp/test_lancedb")
        mock_table = MagicMock()
        mock_db = MagicMock()
        mock_db.open_table.return_value = mock_table
        fake_lancedb = MagicMock()
        fake_lancedb.connect.return_value = mock_db
        with patch.dict("sys.modules", {"lancedb": fake_lancedb}):
            result = store._get_table()
        assert result is mock_table
        assert store._table is mock_table
        fake_lancedb.connect.assert_called_once_with("/tmp/test_lancedb")

    def test_creates_table_when_missing(self):
        store = VectorStore(db_path="/tmp/test_lancedb")
        mock_table = MagicMock()
        mock_db = MagicMock()
        mock_db.open_table.side_effect = Exception("table not found")
        mock_db.create_table.return_value = mock_table
        fake_lancedb = MagicMock()
        fake_lancedb.connect.return_value = mock_db
        with patch.dict("sys.modules", {"lancedb": fake_lancedb}):
            result = store._get_table()
        assert result is mock_table
        mock_db.create_table.assert_called_once()
        assert "knowledge_embeddings" in mock_db.create_table.call_args[0]


class TestVectorStoreUpsertSuccess:
    def test_inserts_new_row(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value = []
        store._table = mock_table
        assert store.upsert("id1", "c1", "text", [0.1] * 384, {"k": "v"}) is True
        mock_table.delete.assert_not_called()
        mock_table.add.assert_called_once()

    def test_replaces_existing_row(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value = [{"id": "id1"}]
        store._table = mock_table
        assert store.upsert("id1", "c1", "text", [0.1] * 384) is True
        mock_table.delete.assert_called_once()
        mock_table.add.assert_called_once()


class TestVectorStoreSearchSuccess:
    def test_search_without_generation(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value = [{"id": "a"}]
        store._table = mock_table
        result = store.search("c1", [0.1] * 384, limit=5)
        assert result == [{"id": "a"}]

    def test_search_with_generation(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.return_value.where.return_value.where.return_value.limit.return_value.to_list.return_value = [{"id": "b"}]
        store._table = mock_table
        result = store.search("c1", [0.1] * 384, limit=5, generation_id="gen-1")
        assert result == [{"id": "b"}]


class TestVectorStoreDeleteSuccess:
    def test_delete_returns_true(self):
        store = VectorStore()
        mock_table = MagicMock()
        store._table = mock_table
        assert store.delete("id1") is True
        mock_table.delete.assert_called_once_with("id = 'id1'")


# ── embeddings ───────────────────────────────────────────────────────


class TestEmbeddingServiceOnnx:
    def test_load_model_initializes_session(self):
        svc = EmbeddingService()
        fake_session = MagicMock()
        fake_tokenizer = MagicMock()
        fake_ort = MagicMock()
        fake_ort.InferenceSession.return_value = fake_session
        fake_tf = MagicMock()
        fake_tf.AutoTokenizer.from_pretrained.return_value = fake_tokenizer
        with patch.dict("sys.modules", {"onnxruntime": fake_ort, "transformers": fake_tf}):
            svc._load_model()
        assert svc._session is fake_session
        assert svc._tokenizer is fake_tokenizer

    def test_onnx_embed_produces_384_dim_vectors(self):
        svc = EmbeddingService()
        svc._tokenizer = MagicMock(
            return_value={
                "input_ids": np.zeros((2, 4), dtype=np.int64),
                "attention_mask": np.ones((2, 4), dtype=np.int64),
            }
        )
        fake_session = MagicMock()
        fake_session.run.return_value = [np.ones((2, 4, 384), dtype=np.float32)]
        svc._session = fake_session
        result = svc._onnx_embed(["hello", "world"])
        assert len(result) == 2
        for vec in result:
            assert len(vec) == 384

    def test_embed_uses_onnx_when_loaded(self):
        svc = EmbeddingService()
        svc._session = MagicMock()
        svc._tokenizer = MagicMock()
        with patch.object(svc, "_onnx_embed", return_value=[[0.1] * 384]) as mock_onnx:
            result = svc.embed(["hello"])
        mock_onnx.assert_called_once_with(["hello"])
        assert len(result) == 1

    def test_fallback_embed_zero_norm_skips_normalization(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        fake_rng = MagicMock()
        fake_rng.normal.return_value = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        with patch("ibreeze.knowledge.embeddings.np.random.default_rng", return_value=fake_rng):
            result = svc.embed(["text"])
        assert len(result) == 1
        assert len(result[0]) == EMBEDDING_DIM


# ── hybrid_search ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHybridSearchCandidateFilter:
    async def test_filters_to_authorized_candidates(self, db):
        with (
            patch("ibreeze.knowledge.hybrid_search.search_fts", return_value=[{"id": "a"}, {"id": "b"}]),
            patch("ibreeze.knowledge.hybrid_search.get_embedding_service") as mock_emb,
            patch("ibreeze.knowledge.hybrid_search.get_vector_store") as mock_vs,
        ):
            mock_emb.return_value.embed_single.return_value = [0.1] * 384
            mock_vs.return_value.search.return_value = [{"id": "b"}, {"id": "c"}]
            result = await hybrid_search(db, "c1", "query", candidate_ids=["b"])
        assert len(result) == 1
        assert result[0]["id"] == "b"
        assert result[0]["rrf_score"] == pytest.approx(2 / 61)


@pytest.mark.asyncio
class TestHybridSearchAccessLog:
    async def test_writes_access_log_when_run_and_employee_set(self, db, published_profile):
        company_id = (await (await db.execute("SELECT id FROM companies LIMIT 1")).fetchone())["id"]
        employee_id = (await (await db.execute("SELECT id FROM employees LIMIT 1")).fetchone())["id"]
        run_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        now = "2026-01-01T00:00:00.000000Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO agent_runs
                   (id, company_id, company_task_id, work_item_id, employee_id,
                    conversation_id, availability_snapshot_id, execution_snapshot_id,
                    run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                    status, attempt, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'company_plan', 'codex_cli',
                           '{}', ?, 'queued', 1, ?, ?, 1)""",
                (
                    run_id,
                    company_id,
                    task_id,
                    task_id,
                    employee_id,
                    str(uuid.uuid4()),
                    "avail",
                    "exec",
                    _sha256("spec"),
                    now,
                    now,
                ),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()

        with (
            patch("ibreeze.knowledge.hybrid_search.search_fts", return_value=[{"id": "a"}]),
            patch("ibreeze.knowledge.hybrid_search.get_embedding_service") as mock_emb,
            patch("ibreeze.knowledge.hybrid_search.get_vector_store") as mock_vs,
        ):
            mock_emb.return_value.embed_single.return_value = [0.1] * 384
            mock_vs.return_value.search.return_value = [{"id": "a"}]
            result = await hybrid_search(
                db,
                company_id,
                "query",
                run_id=run_id,
                employee_id=employee_id,
                department_id=None,
                company_task_id=task_id,
            )
        assert len(result) == 1
        log_count = (await (await db.execute("SELECT COUNT(*) AS cnt FROM knowledge_access_logs")).fetchone())["cnt"]
        assert log_count == 1


# ── generation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCountLanceDbItems:
    async def test_returns_row_count(self):
        mock_table = MagicMock()
        mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value = [{"id": "a"}, {"id": "b"}]
        mock_db = MagicMock()
        mock_db.open_table.return_value = mock_table
        fake_lancedb = MagicMock()
        fake_lancedb.connect.return_value = mock_db
        with patch.dict("sys.modules", {"lancedb": fake_lancedb}):
            assert await count_lancedb_items("c1") == 2

    async def test_returns_zero_when_open_table_fails(self):
        mock_db = MagicMock()
        mock_db.open_table.side_effect = Exception("no table")
        fake_lancedb = MagicMock()
        fake_lancedb.connect.return_value = mock_db
        with patch.dict("sys.modules", {"lancedb": fake_lancedb}):
            assert await count_lancedb_items("c1") == 0


@pytest.mark.asyncio
class TestCountLanceDbItemsForGeneration:
    async def test_returns_row_count(self):
        mock_table = MagicMock()
        mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value = [{"id": "a"}]
        mock_db = MagicMock()
        mock_db.open_table.return_value = mock_table
        fake_lancedb = MagicMock()
        fake_lancedb.connect.return_value = mock_db
        with patch.dict("sys.modules", {"lancedb": fake_lancedb}):
            assert await count_lancedb_items_for_generation("g1") == 1

    async def test_returns_zero_when_open_table_fails(self):
        mock_db = MagicMock()
        mock_db.open_table.side_effect = Exception("no table")
        fake_lancedb = MagicMock()
        fake_lancedb.connect.return_value = mock_db
        with patch.dict("sys.modules", {"lancedb": fake_lancedb}):
            assert await count_lancedb_items_for_generation("g1") == 0
