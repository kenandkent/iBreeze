"""Tests for knowledge sub-modules: chunker, embeddings, vector_store, hybrid_search, text_search."""

from __future__ import annotations

import hashlib
import json
import uuid
from unittest.mock import MagicMock, patch

import aiosqlite
import numpy as np
import pytest

from ibreeze.knowledge.chunker import chunk_code, chunk_markdown, chunk_text
from ibreeze.knowledge.embeddings import EmbeddingService, get_embedding_service
from ibreeze.knowledge.hybrid_search import (
    RRF_K,
    _id,
    _now,
    _sha256,
    reciprocal_rank_fusion,
)
from ibreeze.knowledge.text_search import search_fts
from ibreeze.knowledge.vector_store import VectorStore, _escape_sql_literal, get_vector_store


class TestChunkMarkdown:
    def test_empty_text_returns_empty(self):
        assert chunk_markdown("") == []

    def test_short_text_single_chunk(self):
        result = chunk_markdown("Hello world")
        assert len(result) == 1
        assert result[0]["text"] == "Hello world"
        assert result[0]["token_count"] >= 1

    def test_multiple_paragraphs_within_limit(self):
        text = "Para 1\n\nPara 2\n\nPara 3"
        result = chunk_markdown(text, max_tokens=10000)
        assert len(result) == 1

    def test_paragraphs_exceeding_limit_splits(self):
        text = "A" * 4000 + "\n\n" + "B" * 4000
        result = chunk_markdown(text, max_tokens=800)
        assert len(result) >= 2

    def test_token_count_estimation(self):
        text = "test"
        result = chunk_markdown(text, max_tokens=10000)
        assert result[0]["token_count"] >= 1

    def test_strips_whitespace(self):
        text = "  Hello  \n\n  World  "
        result = chunk_markdown(text, max_tokens=10000)
        assert result[0]["text"] == "Hello  \n\n  World"


class TestChunkCode:
    def test_empty_code(self):
        assert chunk_code("") == []

    def test_single_function(self):
        code = "def hello():\n    print('hi')"
        result = chunk_code(code)
        assert len(result) == 1
        assert "def" in result[0]["text"]
        assert result[0]["language"] == ""

    def test_multiple_functions_split(self):
        code = "def f1():\n" + "    pass\n" * 300 + "\ndef f2():\n    pass"
        result = chunk_code(code, max_tokens=100)
        assert len(result) >= 2

    def test_class_boundary(self):
        code = "class Foo:\n" + "    pass\n" * 300 + "\nclass Bar:\n    pass"
        result = chunk_code(code, max_tokens=100)
        assert len(result) >= 2

    def test_async_def_boundary(self):
        code = "async def foo():\n" + "    await bar()\n" * 300 + "\nasync def baz():\n    pass"
        result = chunk_code(code, max_tokens=100)
        assert len(result) >= 2

    def test_language_propagated(self):
        code = "def f(): pass"
        result = chunk_code(code, language="python")
        assert result[0]["language"] == "python"

    def test_function_export_boundary(self):
        code = "export function foo() {\n" + "  const x = 1;\n" * 300 + "\n}\nexport function bar() {}"
        result = chunk_code(code, max_tokens=100)
        assert len(result) >= 2

    def test_token_estimation(self):
        code = "hello world"
        result = chunk_code(code)
        assert result[0]["token_count"] >= 1


class TestChunkText:
    def test_delegates_to_chunk_markdown(self):
        text = "Hello\n\nWorld"
        result = chunk_text(text)
        expected = chunk_markdown(text)
        assert result == expected


class TestEscapeSqlLiteral:
    def test_no_escaping_needed(self):
        assert _escape_sql_literal("hello") == "hello"

    def test_escapes_single_quotes(self):
        assert _escape_sql_literal("it's") == "it''s"

    def test_multiple_quotes(self):
        assert _escape_sql_literal("a'b'c") == "a''b''c"


class TestVectorStoreInit:
    def test_default_path(self):
        store = VectorStore()
        assert store._db_path == "~/.ibreeze/lancedb"
        assert store._table is None

    def test_custom_path(self):
        store = VectorStore(db_path="/tmp/test_lancedb")
        assert store._db_path == "/tmp/test_lancedb"


class TestVectorStoreGetTable:
    def test_returns_none_on_import_error(self):
        store = VectorStore()
        with patch.dict("sys.modules", {"lancedb": None}):
            result = store._get_table()
        assert result is None

    def test_caches_table(self):
        store = VectorStore()
        mock_table = MagicMock()
        store._table = mock_table
        assert store._get_table() is mock_table


class TestVectorStoreUpsert:
    def test_returns_false_when_no_table(self):
        store = VectorStore()
        with patch.object(store, "_get_table", return_value=None):
            assert store.upsert("id1", "c1", "text", [0.1] * 384) is False

    def test_returns_false_on_exception(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.side_effect = Exception("db error")
        with patch.object(store, "_get_table", return_value=mock_table):
            assert store.upsert("id1", "c1", "text", [0.1] * 384) is False


class TestVectorStoreSearch:
    def test_returns_empty_when_no_table(self):
        store = VectorStore()
        with patch.object(store, "_get_table", return_value=None):
            assert store.search("c1", [0.1] * 384) == []

    def test_returns_empty_on_exception(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.search.side_effect = Exception("db error")
        with patch.object(store, "_get_table", return_value=mock_table):
            assert store.search("c1", [0.1] * 384) == []


class TestVectorStoreDelete:
    def test_returns_false_when_no_table(self):
        store = VectorStore()
        with patch.object(store, "_get_table", return_value=None):
            assert store.delete("id1") is False

    def test_returns_false_on_exception(self):
        store = VectorStore()
        mock_table = MagicMock()
        mock_table.delete.side_effect = Exception("db error")
        with patch.object(store, "_get_table", return_value=mock_table):
            assert store.delete("id1") is False


class TestGetVectorStore:
    def test_singleton(self):
        import ibreeze.knowledge.vector_store as mod
        mod._vector_store = None
        s1 = get_vector_store()
        s2 = get_vector_store()
        assert s1 is s2
        mod._vector_store = None


class TestEmbeddingService:
    def test_init_defaults(self):
        svc = EmbeddingService()
        assert svc._session is None
        assert svc._tokenizer is None
        assert svc._model_path is None

    def test_fallback_embed(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        with patch("builtins.hash", return_value=1234567890123456789):
            result = svc.embed(["hello world"])
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_fallback_embed_multiple(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        with patch("builtins.hash", side_effect=[1234567890123456789, 9876543210987654321]):
            result = svc.embed(["hello", "world"])
        assert len(result) == 2
        assert result[0] != result[1]

    def test_embed_single(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        with patch("builtins.hash", return_value=999999999999999999):
            result = svc.embed_single("test text")
        assert len(result) == 384

    def test_load_model_caches(self):
        svc = EmbeddingService()
        svc._session = "fallback"
        svc._load_model()
        assert svc._session == "fallback"

    def test_mean_pooling(self):
        svc = EmbeddingService()
        token_emb = np.random.rand(2, 5, 64).astype(np.float32)
        attn_mask = np.array([[1, 1, 1, 0, 0], [1, 1, 1, 1, 1]], dtype=np.int64)
        result = svc._mean_pooling(token_emb, attn_mask)
        assert result.shape == (2, 64)


class TestGetEmbeddingService:
    def test_singleton(self):
        import ibreeze.knowledge.embeddings as mod
        mod._embedding_service = None
        s1 = get_embedding_service()
        s2 = get_embedding_service()
        assert s1 is s2
        mod._embedding_service = None


class TestReciprocalRankFusion:
    def test_empty_lists(self):
        assert reciprocal_rank_fusion([]) == []

    def test_single_list(self):
        items = [{"id": "a", "score": 1}, {"id": "b", "score": 2}]
        result = reciprocal_rank_fusion([items])
        assert len(result) == 2
        assert result[0]["rrf_score"] > result[1]["rrf_score"]

    def test_two_lists_merge(self):
        list1 = [{"id": "a"}, {"id": "b"}]
        list2 = [{"id": "b"}, {"id": "c"}]
        result = reciprocal_rank_fusion([list1, list2])
        ids = [r["id"] for r in result]
        assert "b" in ids
        assert "a" in ids
        assert "c" in ids

    def test_deduplication(self):
        list1 = [{"id": "a", "extra": 1}]
        list2 = [{"id": "a", "extra": 2}]
        result = reciprocal_rank_fusion([list1, list2])
        assert len(result) == 1
        assert result[0]["rrf_score"] > 0

    def test_custom_k(self):
        items = [{"id": "a"}]
        result = reciprocal_rank_fusion([items], k=10)
        assert result[0]["rrf_score"] == pytest.approx(1.0 / (10 + 1))

    def test_items_without_id(self):
        items = [{"name": "no-id"}]
        result = reciprocal_rank_fusion([items])
        assert len(result) == 1


class TestHybridHelpers:
    def test_id_returns_uuid(self):
        val = _id()
        uuid.UUID(val)  # should not raise

    def test_now_returns_iso_string(self):
        val = _now()
        assert "T" in val
        assert val.endswith("Z")

    def test_sha256_deterministic(self):
        a = _sha256("hello")
        b = _sha256("hello")
        assert a == b
        assert len(a) == 64

    def test_sha256_varies(self):
        assert _sha256("a") != _sha256("b")


class TestTextSearchFTS:
    @pytest.mark.asyncio
    async def test_search_fts_empty_table(self, db: aiosqlite.Connection):
        result = await search_fts(db, "test", "company1")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_fts_with_generation_filter(self, db: aiosqlite.Connection):
        result = await search_fts(
            db, "test", "company1", generation_id="gen1"
        )
        assert result == []
