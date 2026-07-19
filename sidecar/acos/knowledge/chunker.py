"""知识分块（Phase 8 P8-T2）。

分块是 CPU 密集工作，用 ProcessPoolExecutor 隔离，不在主 asyncio 事件循环里跑同步计算。
"""

from __future__ import annotations

import re
from concurrent.futures import ProcessPoolExecutor

_CHUNK_TARGET = 400
_OVERLAP = 80

_SENT_RE = re.compile(r"[。！？\.\!\?；;\n]")


def _chunk_text(text: str, target: int = _CHUNK_TARGET, overlap: int = _OVERLAP) -> list[str]:
    """按句子边界切分，靠近 target 长度聚合，带重叠窗口。"""
    if not text or not text.strip():
        return []
    pieces = _SENT_RE.split(text)
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        seg = piece.strip()
        if not seg:
            continue
        if buf and len(buf) + len(seg) > target:
            chunks.append(buf)
            buf = buf[-overlap:] if overlap else ""
        buf = (buf + seg) if buf else seg
    if buf:
        chunks.append(buf)
    return chunks


class Chunker:
    """分块器，使用进程池隔离 CPU 密集工作。"""

    def __init__(self, target: int = _CHUNK_TARGET, overlap: int = _OVERLAP) -> None:
        self._target = target
        self._overlap = overlap
        self._executor = ProcessPoolExecutor(max_workers=2)

    async def chunk(self, text: str) -> list[str]:
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, _chunk_text, text, self._target, self._overlap
        )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
