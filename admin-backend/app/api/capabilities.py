import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.capability import Capability, CapabilityVersion, SkillBinding
from app.schemas.capability import (
    CapabilityCreate,
    CapabilityUpdate,
    CapabilityVersionCreate,
    SkillBindingCreate,
)

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])

VALID_TRANSITIONS = {
    "draft": {"review"},
    "review": {"published", "draft"},
    "published": {"deprecated"},
    "deprecated": {"archived"},
    "archived": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(c: Capability) -> dict:
    return {
        "capability_id": c.capability_id,
        "company_id": c.company_id,
        "name": c.name,
        "description": c.description,
        "status": c.status,
        "current_version": c.current_version,
        "version": c.version,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


@router.get("")
async def list_capabilities(
    company_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(Capability)
    if company_id:
        q = q.where(Capability.company_id == company_id)
    if status:
        q = q.where(Capability.status == status)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_dict(c) for c in result.scalars().all()]


@router.post("", status_code=201)
async def create_capability(
    req: CapabilityCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    cap_id = str(uuid.uuid4())
    now = _now()
    cap = Capability(
        capability_id=cap_id,
        company_id=req.company_id,
        name=req.name,
        description=req.description,
        status="draft",
        current_version=1,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(cap)
    await db.commit()
    await db.refresh(cap)
    return _to_dict(cap)


@router.get("/{capability_id}")
async def get_capability(
    capability_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(Capability).where(Capability.capability_id == capability_id)
    )
    cap = result.scalar_one_or_none()
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    return _to_dict(cap)


@router.put("/{capability_id}")
async def update_capability(
    capability_id: str,
    req: CapabilityUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(
        select(Capability).where(Capability.capability_id == capability_id)
    )
    cap = result.scalar_one_or_none()
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    if req.name is not None:
        cap.name = req.name
    if req.description is not None:
        cap.description = req.description
    cap.updated_at = _now()
    cap.version = cap.version + 1
    await db.commit()
    await db.refresh(cap)
    return _to_dict(cap)


async def _transition(capability_id: str, target_status: str, db: AsyncSession) -> Capability:
    result = await db.execute(
        select(Capability).where(Capability.capability_id == capability_id)
    )
    cap = result.scalar_one_or_none()
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    allowed = VALID_TRANSITIONS.get(cap.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {cap.status} to {target_status}",
        )
    cap.status = target_status
    cap.updated_at = _now()
    cap.version = cap.version + 1
    await db.commit()
    await db.refresh(cap)
    return cap


@router.post("/{capability_id}/submit-review")
async def submit_review(
    capability_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    cap = await _transition(capability_id, "review", db)
    return _to_dict(cap)


@router.post("/{capability_id}/publish")
async def publish(
    capability_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    cap = await _transition(capability_id, "published", db)
    return _to_dict(cap)


@router.post("/{capability_id}/deprecate")
async def deprecate(
    capability_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    cap = await _transition(capability_id, "deprecated", db)
    return _to_dict(cap)


@router.post("/{capability_id}/archive")
async def archive(
    capability_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    cap = await _transition(capability_id, "archived", db)
    return _to_dict(cap)


@router.get("/{capability_id}/versions")
async def list_versions(
    capability_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(CapabilityVersion)
        .where(CapabilityVersion.capability_id == capability_id)
        .order_by(CapabilityVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "id": v.id,
            "capability_id": v.capability_id,
            "version": v.version,
            "content": v.content,
            "checksum": v.checksum,
            "created_at": v.created_at,
        }
        for v in versions
    ]


@router.post("/{capability_id}/versions", status_code=201)
async def create_version(
    capability_id: str,
    req: CapabilityVersionCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(
        select(Capability).where(Capability.capability_id == capability_id)
    )
    cap = result.scalar_one_or_none()
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")

    new_version = cap.current_version + 1
    ver = CapabilityVersion(
        capability_id=capability_id,
        version=new_version,
        content=req.content,
        checksum=req.checksum,
        created_at=_now(),
    )
    db.add(ver)
    cap.current_version = new_version
    cap.updated_at = _now()
    await db.commit()
    await db.refresh(ver)
    return {
        "id": ver.id,
        "capability_id": ver.capability_id,
        "version": ver.version,
        "content": ver.content,
        "checksum": ver.checksum,
        "created_at": ver.created_at,
    }


@router.get("/{capability_id}/bindings")
async def list_bindings(
    capability_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(SkillBinding)
        .where(SkillBinding.capability_id == capability_id)
        .order_by(SkillBinding.ordinal)
    )
    bindings = result.scalars().all()
    return [
        {
            "binding_id": b.binding_id,
            "capability_id": b.capability_id,
            "skill_id": b.skill_id,
            "ordinal": b.ordinal,
            "created_at": b.created_at,
        }
        for b in bindings
    ]


@router.post("/{capability_id}/bindings", status_code=201)
async def create_binding(
    capability_id: str,
    req: SkillBindingCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    binding_id = str(uuid.uuid4())
    binding = SkillBinding(
        binding_id=binding_id,
        capability_id=capability_id,
        skill_id=req.skill_id,
        ordinal=req.ordinal,
        created_at=_now(),
    )
    db.add(binding)
    await db.commit()
    await db.refresh(binding)
    return {
        "binding_id": binding.binding_id,
        "capability_id": binding.capability_id,
        "skill_id": binding.skill_id,
        "ordinal": binding.ordinal,
        "created_at": binding.created_at,
    }
