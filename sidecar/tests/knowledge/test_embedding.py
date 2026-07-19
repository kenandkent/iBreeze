"""P8-T3 embedding 测试：真实本地向量、维度确定、语义相关。"""

from __future__ import annotations

import pytest

from acos.knowledge.embedding import EmbeddingService, LocalEmbedding


async def test_local_embedding_dim() -> None:
    emb = LocalEmbedding()
    v = await emb.embed_text("hello world")
    assert len(v) == emb.dim
    assert all(isinstance(x, float) for x in v)


async def test_embedding_deterministic() -> None:
    emb = LocalEmbedding()
    a = await emb.embed_text("知识库安全策略")
    b = await emb.embed_text("知识库安全策略")
    assert a == b


async def test_embedding_semantic_similarity() -> None:
    emb = LocalEmbedding()
    same = await emb.embed_text("RAG 检索增强生成")
    near = await emb.embed_text("RAG 检索增强生成方法")
    diff = await emb.embed_text("财务报表季度营收分析")
    import math

    def cos(x, y):
        dot = sum(a * b for a, b in zip(x, y))
        nx = math.sqrt(sum(a * a for a in x))
        ny = math.sqrt(sum(b * b for b in y))
        return dot / (nx * ny)

    assert cos(same, near) > cos(same, diff)


async def test_embedding_batch() -> None:
    emb = LocalEmbedding()
    out = await emb.embed(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == emb.dim for v in out)


async def test_backward_compat_embedding_service() -> None:
    svc = EmbeddingService()
    v = await svc.embed_text("hello")
    assert len(v) == svc.VECTOR_DIM
    from acos.knowledge.models import KnowledgeDocument

    n = await svc.embed_document(KnowledgeDocument(content="x" * 1200))
    assert n == 3
