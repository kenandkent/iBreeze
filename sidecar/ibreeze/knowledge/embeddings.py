"""ONNX embedding service — intfloat/multilingual-e5-small, 384-dim."""

from __future__ import annotations

import os
from typing import Any, cast

import numpy as np

EMBEDDING_DIM = 384  # multilingual-e5-small

_MAX_SEQ_LEN = 512


class EmbeddingService:
    """ONNX-based embedding service using intfloat/multilingual-e5-small."""

    def __init__(self, model_path: str | None = None) -> None:
        self._session: Any = None
        self._tokenizer: Any = None
        self._model_path = model_path

    def _load_model(self) -> None:
        if self._session is not None or self._session == "fallback":
            return
        try:
            import onnxruntime as ort  # type: ignore[import-untyped]
            from transformers import AutoTokenizer  # type: ignore[import-not-found]

            model_path = self._model_path or os.path.expanduser(
                "~/.ibreeze/models/multilingual-e5-small.onnx"
            )
            self._session = ort.InferenceSession(model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                "intfloat/multilingual-e5-small"
            )
        except Exception:
            self._session = "fallback"

    @staticmethod
    def _mean_pooling(
        token_embeddings: np.ndarray, attention_mask: np.ndarray
    ) -> np.ndarray:
        """Mean pooling over token embeddings, masked by attention_mask."""
        mask_expanded = np.expand_dims(attention_mask, -1).astype(np.float32)
        summed = np.sum(token_embeddings * mask_expanded, axis=1)
        counts = np.clip(mask_expanded.sum(axis=1), 1e-9, None)
        return summed / counts

    def _onnx_embed(self, texts: list[str]) -> list[list[float]]:
        """Run actual ONNX inference with tokenization and mean pooling."""
        inputs = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=_MAX_SEQ_LEN,
            return_tensors="np",
        )
        input_ids = inputs["input_ids"].astype(np.int64)
        attention_mask = inputs["attention_mask"].astype(np.int64)

        outputs = self._session.run(
            None,
            {"input_ids": input_ids, "attention_mask": attention_mask},
        )
        token_embeddings = outputs[0]
        pooled = self._mean_pooling(token_embeddings, attention_mask)

        # L2 normalize
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        pooled = pooled / np.clip(norms, 1e-9, None)
        return cast("list[list[float]]", pooled.tolist())

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        self._load_model()
        if self._session == "fallback" or self._session is None:
            return self._fallback_embed(texts)
        return self._onnx_embed(texts)

    def _fallback_embed(self, texts: list[str]) -> list[list[float]]:
        """Deterministic pseudo-embedding based on text hash."""
        import hashlib
        results: list[list[float]] = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
            rng = np.random.default_rng(seed)
            vec = rng.normal(size=EMBEDDING_DIM).astype(np.float32)
            norms = np.linalg.norm(vec)
            if norms > 0:
                vec = vec / norms
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
