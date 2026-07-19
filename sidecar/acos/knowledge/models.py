"""知识库 dataclass。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class KnowledgeDocument:
    document_id: str = ""
    company_id: str = ""
    title: str = ""
    content: str = ""
    source_type: str = "manual"
    source_path: Optional[str] = None
    source_category: str = "custom"
    visibility: str = "company"
    embedding_generation_id: Optional[str] = None
    embedding_status: str = "pending"
    checksum: str = ""
    version: int = 1
    status: str = "active"

    def compute_checksum(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class KnowledgeChunk:
    chunk_id: str = ""
    document_id: str = ""
    company_id: str = ""
    content: str = ""
    chunk_index: int = 0
    embedding_status: str = "pending"
