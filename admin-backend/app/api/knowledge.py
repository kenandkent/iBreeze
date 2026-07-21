import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import KnowledgeDocumentCreate, KnowledgeDocumentUpdate

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(d: KnowledgeDocument) -> dict:
    return {
        "knowledge_id": d.knowledge_id,
        "company_id": d.company_id,
        "title": d.title,
        "content": d.content,
        "source_type": d.source_type,
        "source_id": d.source_id,
        "category": d.category,
        "status": d.status,
        "governance_confirmed": d.governance_confirmed,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


@router.get("/documents")
async def list_documents(
    company_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(KnowledgeDocument)
    if company_id:
        q = q.where(KnowledgeDocument.company_id == company_id)
    if status:
        q = q.where(KnowledgeDocument.status == status)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_dict(d) for d in result.scalars().all()]


@router.get("/documents/{knowledge_id}")
async def get_document(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_id == knowledge_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _to_dict(doc)


@router.post("/documents", status_code=201)
async def create_document(
    req: KnowledgeDocumentCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    doc_id = str(uuid.uuid4())
    now = _now()
    doc = KnowledgeDocument(
        knowledge_id=doc_id,
        company_id=req.company_id,
        title=req.title,
        content=req.content,
        source_type=req.source_type,
        source_id=req.source_id,
        category=req.category,
        status="active",
        governance_confirmed=0,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return _to_dict(doc)


@router.put("/documents/{knowledge_id}")
async def update_document(
    knowledge_id: str,
    req: KnowledgeDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_id == knowledge_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if req.title is not None:
        doc.title = req.title
    if req.content is not None:
        doc.content = req.content
    if req.category is not None:
        doc.category = req.category
    doc.updated_at = _now()
    await db.commit()
    await db.refresh(doc)
    return _to_dict(doc)


@router.delete("/documents/{knowledge_id}", status_code=204)
async def delete_document(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_id == knowledge_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()


@router.post("/documents/{knowledge_id}/confirm")
async def confirm_document(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_id == knowledge_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.governance_confirmed = 1
    doc.updated_at = _now()
    await db.commit()
    await db.refresh(doc)
    return _to_dict(doc)


@router.post("/documents/{knowledge_id}/reject")
async def reject_document(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_id == knowledge_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.governance_confirmed = -1
    doc.updated_at = _now()
    await db.commit()
    await db.refresh(doc)
    return _to_dict(doc)


@router.post("/reindex")
async def reindex(
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    return {"status": "reindex queued"}


@router.post("/sources/{source_id}/delete")
async def delete_source(
    source_id: str,
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    return {"status": "source deletion queued", "source_id": source_id}


@router.post("/ingest/{job_id}/retry")
async def retry_ingest(
    job_id: str,
    _user: AdminUser = Depends(require_permission("knowledge")),
):
    return {"status": "ingest retry queued", "job_id": job_id}
