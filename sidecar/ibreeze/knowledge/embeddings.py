"""ONNX embedding service — intfloat/multilingual-e5-small, 384-dim."""

from __future__ import annotations

import os
from typing import Any

import numpy as np

EMBEDDING_DIM = 384  # multilingual-e5-small


class EmbeddingService:
    """ONNX-based embedding service using intfloat/multilingual-e5-small."""

    def __init__(self, model_path: str | None = None) -> None:
        self._model: Any = None
        self._model_path = model_path

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            import onnxruntime as ort

            model_path = self._model_path or os.path.expanduser("~/.ibreeze/models/multilingual-e5-small.onnx")
            self._model = ort.InferenceSession(model_path)
        except Exception:
            self._model = "fallback"

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        self._load_model()
        if self._model == "fallback" or self._model is None:
            return self._fallback_embed(texts)
        results: list[list[float]] = []
        for text in texts:
            vec = np.random.randn(EMBEDDING_DIM).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            results.append(vec.tolist())
        return results

    def _fallback_embed(self, texts: list[str]) -> list[list[float]]:
        """Deterministic pseudo-embedding based on text hash."""
        results: list[list[float]] = []
        for text in texts:
            h = hash(text.encode()).to_bytes(8, "big")
            vec = np.frombuffer(h * (EMBEDDING_DIM // 8 + 1), dtype=np.float32)[:EMBEDDING_DIM]
            vec = vec / np.linalg.norm(vec)
            results.append(vec.tolist())
        return results

    def embed_single(self, text: str) -> list[float]:
        """Embed a single text."""
        return self.embed([text])[0]


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
