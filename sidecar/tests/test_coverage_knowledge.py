"""Tests to improve knowledge module coverage: hybrid_search, vector_store, embeddings."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ibreeze.knowledge.embeddings import EMBEDDING_DIM, EmbeddingService, get_embedding_service
from ibreeze.knowledge.hybrid_search import (
    RRF_K,
    hybrid_search,
    reciprocal_rank_fusion,
)
from ibreeze.knowledge.text_search import search_fts
from ibreeze.knowledge.vector_store import VectorStore, _escape_sql_literal, get_vector_store


# ── Embeddings ─────────────────────────────────────────────────────────


class TestEmbeddingServiceExtended:
    def test_fallback_embed_deterministic(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        r1 = svc.embed(["hello"])
        r2 = svc.embed(["hello"])
        assert r1 == r2

    def test_fallback_embed_normalization(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        result = svc.embed(["test"])
        norm = np.linalg.norm(result[0])
        assert abs(norm - 1.0) < 1e-5

    def test_fallback_embed_multiple_texts(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        result = svc.embed(["hello", "world", "test"])
        assert len(result) == 3
        for vec in result:
            assert len(vec) == EMBEDDING_DIM

    def test_load_model_exception_fallback(self):
        svc = EmbeddingService()
        svc._session = None
        svc._model_path = "/nonexistent/model.onnx"
        svc._load_model()
        assert svc._session == "fallback"

    def test_onnx_embed_not_called_when_fallback(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        with patch.object(svc, "_onnx_embed") as mock_onnx:
            svc.embed(["test"])
            mock_onnx.assert_not_called()

    def test_get_embedding_service_singleton(self):
        import ibreeze.knowledge.embeddings as mod
        mod._embedding_service = None
        svc1 = get_embedding_service()
        svc2 = get_embedding_service()
        assert svc1 is svc2
        mod._embedding_service = None


# ── Vector Store ───────────────────────────────────────────────────────


class TestVectorStoreExtended:
    def test_escape_sql_literal(self):
        assert _escape_sql_literal("hello") == "hello"
        assert _escape_sql_literal("it's") == "it''s"
        assert _escape_sql_literal("a'b'c") == "a''b''c"

    def test_upsert_no_table(self):
        store = VectorStore()
        store._table = None
        with patch.object(store, "_get_table", return_value=None):
            result = store.upsert("id1", "comp1", "text", [0.1] * 384)
            assert result is False

    def test_search_no_table(self):
        store = VectorStore()
        store._table = None
        with patch.object(store, "_get_table", return_value=None):
            result = store.search("comp1", [0.1] * 384)
            assert result == []

    def test_delete_no_table(self):
        store = VectorStore()
        store._table = None
        with patch.object(store, "_get_table", return_value=None):
            result = store.delete("id1")
            assert result is False

    def test_upsert_exception(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.side_effect = Exception("db error")
        store._table = mock_table
        result = store.upsert("id1", "comp1", "text", [0.1] * 384)
        assert result is False

    def test_search_exception(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.side_effect = Exception("db error")
        store._table = mock_table
        result = store.search("comp1", [0.1] * 384)
        assert result == []

    def test_delete_exception(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.delete.side_effect = Exception("db error")
        store._table = mock_table
        result = store.delete("id1")
        assert result is False

    def test_get_table_cache(self):
        store = VectorStore()
        mock_table = MagicMock()
        store._table = mock_table
        assert store._get_table() is mock_table

    def test_get_vector_store_singleton(self):
        import ibreeze.knowledge.vector_store as mod
        mod._vector_store = None
        vs1 = get_vector_store()
        vs2 = get_vector_store()
        assert vs1 is vs2
        mod._vector_store = None


# ── Hybrid Search ──────────────────────────────────────────────────────


class TestReciprocalRankFusion:
    def test_empty_lists(self):
        result = reciprocal_rank_fusion([])
        assert result == []

    def test_single_list(self):
        items = [{"id": "a", "score": 1.0}, {"id": "b", "score": 0.5}]
        result = reciprocal_rank_fusion([items])
        assert len(result) == 2
        assert result[0]["rrf_score"] > result[1]["rrf_score"]

    def test_fusion_combines_scores(self):
        list1 = [{"id": "a"}, {"id": "b"}]
        list2 = [{"id": "b"}, {"id": "c"}]
        result = reciprocal_rank_fusion([list1, list2])
        ids = [r["id"] for r in result]
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids
        # "b" appears in both lists, should have highest score
        b_score = next(r["rrf_score"] for r in result if r["id"] == "b")
        a_score = next(r["rrf_score"] for r in result if r["id"] == "a")
        assert b_score > a_score

    def test_custom_k(self):
        items = [{"id": "a"}]
        result = reciprocal_rank_fusion([items], k=1)
        assert result[0]["rrf_score"] == 1.0 / (1 + 1)

    def test_deduplication(self):
        list1 = [{"id": "a", "extra": 1}]
        list2 = [{"id": "a", "extra": 2}]
        result = reciprocal_rank_fusion([list1, list2])
        assert len(result) == 1
        # Should keep first occurrence
        assert result[0]["extra"] == 1


@pytest.mark.asyncio
class TestHybridSearch:
    async def test_search_empty_results(self, db, published_profile):
        with patch("ibreeze.knowledge.hybrid_search.search_fts", return_value=[]) as mock_fts, \
             patch("ibreeze.knowledge.hybrid_search.get_embedding_service") as mock_emb, \
             patch("ibreeze.knowledge.hybrid_search.get_vector_store") as mock_vs:
            mock_emb.return_value.embed_single.return_value = [0.1] * 384
            mock_vs.return_value.search.return_value = []
            result = await hybrid_search(
                db, "comp1", "test query",
                candidate_ids=None, generation_id=None,
            )
            assert result == []


# ── Text Search ────────────────────────────────────────────────────────


class TestTextSearch:
    async def test_search_fts_empty(self, db):
        result = await search_fts(db, "test", "comp1")
        assert result == []
