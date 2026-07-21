import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.capability import PromptAsset, PromptAssetVersion
from app.schemas.capability import PromptCreate, PromptUpdate, PromptVersionCreate

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

VALID_TRANSITIONS = {
    "draft": {"review"},
    "review": {"published", "draft"},
    "published": {"deprecated"},
    "deprecated": {"archived"},
    "archived": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(p: PromptAsset) -> dict:
    return {
        "prompt_id": p.prompt_id,
        "company_id": p.company_id,
        "name": p.name,
        "description": p.description,
        "content": p.content,
        "status": p.status,
        "version": p.version,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


@router.get("")
async def list_prompts(
    company_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(PromptAsset)
    if company_id:
        q = q.where(PromptAsset.company_id == company_id)
    if status:
        q = q.where(PromptAsset.status == status)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_dict(p) for p in result.scalars().all()]


@router.post("", status_code=201)
async def create_prompt(
    req: PromptCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    prompt_id = str(uuid.uuid4())
    now = _now()
    prompt = PromptAsset(
        prompt_id=prompt_id,
        company_id=req.company_id,
        name=req.name,
        description=req.description,
        content=req.content,
        status="draft",
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return _to_dict(prompt)


@router.get("/{prompt_id}")
async def get_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(PromptAsset).where(PromptAsset.prompt_id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _to_dict(prompt)


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: str,
    req: PromptUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(select(PromptAsset).where(PromptAsset.prompt_id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if req.name is not None:
        prompt.name = req.name
    if req.description is not None:
        prompt.description = req.description
    if req.content is not None:
        prompt.content = req.content
    prompt.updated_at = _now()
    prompt.version = prompt.version + 1
    await db.commit()
    await db.refresh(prompt)
    return _to_dict(prompt)


@router.post("/{prompt_id}/save-draft")
async def save_draft(
    prompt_id: str,
    req: PromptUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(select(PromptAsset).where(PromptAsset.prompt_id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if prompt.status not in ("draft", "review"):
        raise HTTPException(status_code=400, detail="Can only save-draft from draft or review status")
    if req.name is not None:
        prompt.name = req.name
    if req.description is not None:
        prompt.description = req.description
    if req.content is not None:
        prompt.content = req.content
    prompt.status = "draft"
    prompt.updated_at = _now()
    prompt.version = prompt.version + 1
    await db.commit()
    await db.refresh(prompt)
    return _to_dict(prompt)


async def _transition(prompt_id: str, target_status: str, db: AsyncSession) -> PromptAsset:
    result = await db.execute(select(PromptAsset).where(PromptAsset.prompt_id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    allowed = VALID_TRANSITIONS.get(prompt.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {prompt.status} to {target_status}",
        )
    prompt.status = target_status
    prompt.updated_at = _now()
    prompt.version = prompt.version + 1
    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.post("/{prompt_id}/submit-review")
async def submit_review(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    prompt = await _transition(prompt_id, "review", db)
    return _to_dict(prompt)


@router.post("/{prompt_id}/publish")
async def publish(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    prompt = await _transition(prompt_id, "published", db)
    return _to_dict(prompt)


@router.post("/{prompt_id}/deprecate")
async def deprecate(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    prompt = await _transition(prompt_id, "deprecated", db)
    return _to_dict(prompt)


@router.post("/{prompt_id}/archive")
async def archive(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    prompt = await _transition(prompt_id, "archived", db)
    return _to_dict(prompt)


@router.get("/{prompt_id}/versions")
async def list_versions(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(PromptAssetVersion)
        .where(PromptAssetVersion.prompt_id == prompt_id)
        .order_by(PromptAssetVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "id": v.id,
            "prompt_id": v.prompt_id,
            "version": v.version,
            "content": v.content,
            "checksum": v.checksum,
            "created_at": v.created_at,
        }
        for v in versions
    ]


@router.post("/{prompt_id}/versions", status_code=201)
async def create_version(
    prompt_id: str,
    req: PromptVersionCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(select(PromptAsset).where(PromptAsset.prompt_id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    new_version = prompt.version + 1
    ver = PromptAssetVersion(
        prompt_id=prompt_id,
        version=new_version,
        content=req.content,
        checksum=req.checksum,
        created_at=_now(),
    )
    db.add(ver)
    prompt.version = new_version
    prompt.updated_at = _now()
    await db.commit()
    await db.refresh(ver)
    return {
        "id": ver.id,
        "prompt_id": ver.prompt_id,
        "version": ver.version,
        "content": ver.content,
        "checksum": ver.checksum,
        "created_at": ver.created_at,
    }
