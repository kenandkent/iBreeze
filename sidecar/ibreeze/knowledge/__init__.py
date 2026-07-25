"""Knowledge module — import, chunking, embedding, retrieval and hybrid search."""

from __future__ import annotations

from .chunker import chunk_code, chunk_markdown, chunk_text
from .embeddings import EmbeddingService, get_embedding_service
from .hybrid_search import hybrid_search, reciprocal_rank_fusion
from .service import (
    check_consolidation,
    get_knowledge,
    import_knowledge,
    list_knowledge,
    permitted_knowledge_ids,
    remove_knowledge,
    search_knowledge,
)
from .text_search import search_fts
from .vector_store import VectorStore, get_vector_store

__all__ = [
    "chunk_code",
    "chunk_markdown",
    "chunk_text",
    "check_consolidation",
    "EmbeddingService",
    "get_embedding_service",
    "get_knowledge",
    "get_vector_store",
    "hybrid_search",
    "import_knowledge",
    "list_knowledge",
    "permitted_knowledge_ids",
    "reciprocal_rank_fusion",
    "remove_knowledge",
    "search_knowledge",
    "search_fts",
    "VectorStore",
]
