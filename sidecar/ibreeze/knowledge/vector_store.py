"""LanceDB vector storage for knowledge embeddings."""

from __future__ import annotations

import json
from typing import Any


class VectorStore:
    """LanceDB-based vector storage for knowledge embeddings."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or "~/.ibreeze/lancedb"
        self._table: Any = None

    def _get_table(self) -> Any:
        if self._table is not None:
            return self._table
        try:
            import lancedb

            db = lancedb.connect(self._db_path)
            try:
                self._table = db.open_table("knowledge_embeddings")
            except Exception:
                self._table = db.create_table(
                    "knowledge_embeddings",
                    schema={
                        "id": "string",
                        "company_id": "string",
                        "chunk_text": "string",
                        "embedding": "vector[384]",
                        "metadata": "string",
                    },
                )
            return self._table
        except ImportError:
            return None

    def upsert(
        self,
        id: str,
        company_id: str,
        text: str,
        embedding: list[float],
        metadata: dict | None = None,
    ) -> bool:
        """Insert or update an embedding."""
        table = self._get_table()
        if table is None:
            return False
        try:
            import pyarrow as pa

            data = pa.table(
                {
                    "id": [id],
                    "company_id": [company_id],
                    "chunk_text": [text],
                    "embedding": [embedding],
                    "metadata": [json.dumps(metadata or {}, sort_keys=True)],
                }
            )
            table.add(data)
            return True
        except Exception:
            return False

    def search(
        self,
        company_id: str,
        query_embedding: list[float],
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Search for similar embeddings within a company."""
        table = self._get_table()
        if table is None:
            return []
        try:
            results = table.search(query_embedding).where(f"company_id = '{company_id}'").limit(limit).to_list()
            return results
        except Exception:
            return []

    def delete(self, id: str) -> bool:
        """Delete an embedding by ID."""
        table = self._get_table()
        if table is None:
            return False
        try:
            table.delete(f"id = '{id}'")
            return True
        except Exception:
            return False


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
