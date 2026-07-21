import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.capability import Skill, SkillVersion
from app.schemas.capability import SkillCreate, SkillUpdate, SkillVersionCreate

router = APIRouter(prefix="/api/skills", tags=["skills"])

VALID_TRANSITIONS = {
    "draft": {"review"},
    "review": {"published", "draft"},
    "published": {"deprecated"},
    "deprecated": {"archived"},
    "archived": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(s: Skill) -> dict:
    return {
        "skill_id": s.skill_id,
        "company_id": s.company_id,
        "name": s.name,
        "description": s.description,
        "prompt_asset_id": s.prompt_asset_id,
        "status": s.status,
        "version": s.version,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


@router.get("")
async def list_skills(
    company_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(Skill)
    if company_id:
        q = q.where(Skill.company_id == company_id)
    if status:
        q = q.where(Skill.status == status)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_dict(s) for s in result.scalars().all()]


@router.post("", status_code=201)
async def create_skill(
    req: SkillCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    skill_id = str(uuid.uuid4())
    now = _now()
    skill = Skill(
        skill_id=skill_id,
        company_id=req.company_id,
        name=req.name,
        description=req.description,
        prompt_asset_id=req.prompt_asset_id,
        status="draft",
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _to_dict(skill)


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(Skill).where(Skill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _to_dict(skill)


@router.put("/{skill_id}")
async def update_skill(
    skill_id: str,
    req: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(select(Skill).where(Skill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if req.name is not None:
        skill.name = req.name
    if req.description is not None:
        skill.description = req.description
    if req.prompt_asset_id is not None:
        skill.prompt_asset_id = req.prompt_asset_id
    skill.updated_at = _now()
    skill.version = skill.version + 1
    await db.commit()
    await db.refresh(skill)
    return _to_dict(skill)


@router.post("/{skill_id}/save-draft")
async def save_draft(
    skill_id: str,
    req: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(select(Skill).where(Skill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.status not in ("draft", "review"):
        raise HTTPException(status_code=400, detail="Can only save-draft from draft or review status")
    if req.name is not None:
        skill.name = req.name
    if req.description is not None:
        skill.description = req.description
    if req.prompt_asset_id is not None:
        skill.prompt_asset_id = req.prompt_asset_id
    skill.status = "draft"
    skill.updated_at = _now()
    skill.version = skill.version + 1
    await db.commit()
    await db.refresh(skill)
    return _to_dict(skill)


async def _transition(skill_id: str, target_status: str, db: AsyncSession) -> Skill:
    result = await db.execute(select(Skill).where(Skill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    allowed = VALID_TRANSITIONS.get(skill.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {skill.status} to {target_status}",
        )
    skill.status = target_status
    skill.updated_at = _now()
    skill.version = skill.version + 1
    await db.commit()
    await db.refresh(skill)
    return skill


@router.post("/{skill_id}/submit-review")
async def submit_review(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    skill = await _transition(skill_id, "review", db)
    return _to_dict(skill)


@router.post("/{skill_id}/publish")
async def publish(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    skill = await _transition(skill_id, "published", db)
    return _to_dict(skill)


@router.post("/{skill_id}/deprecate")
async def deprecate(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    skill = await _transition(skill_id, "deprecated", db)
    return _to_dict(skill)


@router.post("/{skill_id}/archive")
async def archive(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    skill = await _transition(skill_id, "archived", db)
    return _to_dict(skill)


@router.get("/{skill_id}/versions")
async def list_versions(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(SkillVersion)
        .where(SkillVersion.skill_id == skill_id)
        .order_by(SkillVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "id": v.id,
            "skill_id": v.skill_id,
            "version": v.version,
            "content": v.content,
            "checksum": v.checksum,
            "created_at": v.created_at,
        }
        for v in versions
    ]


@router.post("/{skill_id}/versions", status_code=201)
async def create_version(
    skill_id: str,
    req: SkillVersionCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(select(Skill).where(Skill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    new_version = skill.version + 1
    ver = SkillVersion(
        skill_id=skill_id,
        version=new_version,
        content=req.content,
        checksum=req.checksum,
        created_at=_now(),
    )
    db.add(ver)
    skill.version = new_version
    skill.updated_at = _now()
    await db.commit()
    await db.refresh(ver)
    return {
        "id": ver.id,
        "skill_id": ver.skill_id,
        "version": ver.version,
        "content": ver.content,
        "checksum": ver.checksum,
        "created_at": ver.created_at,
    }
