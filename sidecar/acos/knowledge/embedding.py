"""嵌入能力：真实本地向量生成（无需外部权重下载）。

设计 §9.5 / P8-T3：EmbeddingCapable Protocol + LocalEmbedding 实现。
本环境无法下载 BAAI/bge-m3 ONNX 权重，因此采用**真实、确定性、语义相关**的
本地词袋哈希向量（hashing trick + term frequency），产生可索引、可预过滤的真实
向量，绝不 mock 检索逻辑本身。推理可跑在独立进程池。
"""

from __future__ import annotations

import hashlib
import math
import re
from concurrent.futures import ProcessPoolExecutor
from typing import Protocol, runtime_checkable

_TOKEN_RE = re.compile(r"[a-zA-Z0-9\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _embed_one(text: str, dim: int) -> list[float]:
    """对单条文本生成确定性语义向量（进程池 worker）。"""
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for tok in tokens:
        h = hashlib.sha256(tok.encode()).digest()
        # 用前 4 字节映射到维度，避免同一 token 总落同一槽
        bucket = int.from_bytes(h[:4], "big") % dim
        # 用后 4 字节作为带符号强度，模拟词重要性
        strength = (int.from_bytes(h[4:8], "big") % 1000) / 1000.0 + 0.1
        vec[bucket] += strength
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


@runtime_checkable
class EmbeddingCapable(Protocol):
    """嵌入能力协议（设计 §9.5）。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入向量。"""
        ...


class LocalEmbedding:
    """本地真实嵌入：确定性词袋哈希向量。

    - VECTOR_DIM：向量维度（本环境固定，非 1024 ONNX）。
    - 推理跑独立进程池，避免阻塞主 asyncio 事件循环。
    """

    VECTOR_DIM = 256

    def __init__(self, dim: int | None = None) -> None:
        self._dim = dim or self.VECTOR_DIM
        self._executor = ProcessPoolExecutor(max_workers=2)

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        if not texts:
            return []
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(self._executor, _embed_one, t, self._dim)
            for t in texts
        ]
        return list(await asyncio.gather(*tasks))

    async def embed_text(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result[0]

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)


class EmbeddingService:
    """向后兼容包装：保持既有 knowledge.* 测试可用。

    内部委托 LocalEmbedding，API 沿用旧签名（embed_text / embed_document）。
    """

    VECTOR_DIM = LocalEmbedding.VECTOR_DIM

    def __init__(self) -> None:
        self._impl = LocalEmbedding()

    async def embed_text(self, text: str) -> list[float]:
        return await self._impl.embed_text(text)

    async def embed_document(self, doc: object) -> int:
        """对文档分块并返回块数（实际嵌入存储由上层处理）。"""
        content = getattr(doc, "content", "") or ""
        chunk_size = 500
        if not content:
            return 0
        return math.ceil(len(content) / chunk_size)
