"""知识库服务。"""

from __future__ import annotations

import uuid
from typing import Optional

import aiosqlite

from acos.knowledge.models import KnowledgeDocument


class KnowledgeService:
    """知识库服务。"""

    async def create_document(
        self, conn: aiosqlite.Connection, doc: KnowledgeDocument
    ) -> KnowledgeDocument:
        if not doc.document_id:
            doc.document_id = str(uuid.uuid4())
        if not doc.checksum:
            doc.checksum = doc.compute_checksum()
        await conn.execute(
            """INSERT INTO knowledge_documents
               (document_id, company_id, title, content, source_type, source_path,
                source_category, visibility, embedding_generation_id, embedding_status,
                checksum, version, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                doc.document_id,
                doc.company_id,
                doc.title,
                doc.content,
                doc.source_type,
                doc.source_path,
                doc.source_category,
                doc.visibility,
                doc.embedding_generation_id,
                doc.embedding_status,
                doc.checksum,
                doc.version,
                doc.status,
            ),
        )
        await conn.commit()
        return doc

    async def update_document(
        self, conn: aiosqlite.Connection, doc: KnowledgeDocument, expected_version: int
    ) -> KnowledgeDocument:
        cursor = await conn.execute(
            """SELECT version FROM knowledge_documents
               WHERE document_id = ? AND company_id = ? AND status = 'active'""",
            (doc.document_id, doc.company_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("document not found")
        if row[0] != expected_version:
            raise ValueError("version conflict")
        new_version = expected_version + 1
        doc.checksum = doc.compute_checksum()
        doc.version = new_version
        await conn.execute(
            """UPDATE knowledge_documents
               SET title = ?, content = ?, source_type = ?, source_path = ?,
                   source_category = ?, visibility = ?, embedding_status = ?,
                   checksum = ?, version = ?, status = ?, updated_at = datetime('now')
               WHERE document_id = ? AND company_id = ?""",
            (
                doc.title,
                doc.content,
                doc.source_type,
                doc.source_path,
                doc.source_category,
                doc.visibility,
                doc.embedding_status,
                doc.checksum,
                new_version,
                doc.status,
                doc.document_id,
                doc.company_id,
            ),
        )
        await conn.commit()
        return doc

    async def delete_document(
        self, conn: aiosqlite.Connection, document_id: str, company_id: str
    ) -> None:
        await conn.execute(
            """UPDATE knowledge_documents SET status = 'deleted', updated_at = datetime('now')
               WHERE document_id = ? AND company_id = ?""",
            (document_id, company_id),
        )
        await conn.commit()

    async def get_document(
        self, conn: aiosqlite.Connection, document_id: str, company_id: str
    ) -> Optional[KnowledgeDocument]:
        cursor = await conn.execute(
            """SELECT document_id, company_id, title, content, source_type, source_path,
                      source_category, visibility, embedding_generation_id, embedding_status,
                      checksum, version, status
               FROM knowledge_documents
               WHERE document_id = ? AND company_id = ? AND status = 'active'""",
            (document_id, company_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return KnowledgeDocument(
            document_id=row[0],
            company_id=row[1],
            title=row[2],
            content=row[3],
            source_type=row[4],
            source_path=row[5],
            source_category=row[6],
            visibility=row[7],
            embedding_generation_id=row[8],
            embedding_status=row[9],
            checksum=row[10],
            version=row[11],
            status=row[12],
        )

    async def search(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        query: str,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[KnowledgeDocument]:
        sql = """SELECT document_id, company_id, title, content, source_type, source_path,
                        source_category, visibility, embedding_generation_id, embedding_status,
                        checksum, version, status
                 FROM knowledge_documents
                 WHERE company_id = ? AND status = 'active'
                   AND (title LIKE ? OR content LIKE ?)"""
        params: list[str] = [company_id, f"%{query}%", f"%{query}%"]
        if category:
            sql += " AND source_category = ?"
            params.append(category)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(str(limit))
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [
            KnowledgeDocument(
                document_id=r[0],
                company_id=r[1],
                title=r[2],
                content=r[3],
                source_type=r[4],
                source_path=r[5],
                source_category=r[6],
                visibility=r[7],
                embedding_generation_id=r[8],
                embedding_status=r[9],
                checksum=r[10],
                version=r[11],
                status=r[12],
            )
            for r in rows
        ]

    async def list_documents(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        category: Optional[str] = None,
    ) -> list[KnowledgeDocument]:
        sql = """SELECT document_id, company_id, title, content, source_type, source_path,
                        source_category, visibility, embedding_generation_id, embedding_status,
                        checksum, version, status
                 FROM knowledge_documents
                 WHERE company_id = ? AND status = 'active'"""
        params: list[str] = [company_id]
        if category:
            sql += " AND source_category = ?"
            params.append(category)
        sql += " ORDER BY created_at DESC"
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [
            KnowledgeDocument(
                document_id=r[0],
                company_id=r[1],
                title=r[2],
                content=r[3],
                source_type=r[4],
                source_path=r[5],
                source_category=r[6],
                visibility=r[7],
                embedding_generation_id=r[8],
                embedding_status=r[9],
                checksum=r[10],
                version=r[11],
                status=r[12],
            )
            for r in rows
        ]
