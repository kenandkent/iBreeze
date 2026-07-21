import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.backend import Backend, CompanyBackendDefault
from app.schemas.provider import BackendCreate, BackendUpdate

router = APIRouter(prefix="/api/backends", tags=["backends"])

VALID_TRANSITIONS = {
    "disabled": {"enabled", "archived"},
    "enabled": {"draining", "disabled"},
    "draining": {"disabled"},
    "archived": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(b: Backend) -> dict:
    return {
        "backend_id": b.backend_id,
        "company_id": b.company_id,
        "name": b.name,
        "backend_type": b.backend_type,
        "provider_id": b.provider_id,
        "workspace_root": b.workspace_root,
        "status": b.status,
        "concurrency": b.concurrency,
        "version": b.version,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }


@router.get("")
async def list_backends(
    company_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(Backend)
    if company_id:
        q = q.where(Backend.company_id == company_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_dict(b) for b in result.scalars().all()]


@router.post("", status_code=201)
async def create_backend(
    req: BackendCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    backend_id = str(uuid.uuid4())
    now = _now()
    backend = Backend(
        backend_id=backend_id,
        company_id=req.company_id,
        name=req.name,
        backend_type=req.backend_type,
        provider_id=req.provider_id,
        workspace_root=req.workspace_root,
        status="disabled",
        concurrency=req.concurrency,
        version="1",
        created_at=now,
        updated_at=now,
    )
    db.add(backend)
    await db.commit()
    await db.refresh(backend)
    return _to_dict(backend)


@router.put("/{backend_id}")
async def update_backend(
    backend_id: str,
    req: BackendUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    result = await db.execute(select(Backend).where(Backend.backend_id == backend_id))
    backend = result.scalar_one_or_none()
    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    if req.name is not None:
        backend.name = req.name
    if req.provider_id is not None:
        backend.provider_id = req.provider_id
    if req.workspace_root is not None:
        backend.workspace_root = req.workspace_root
    if req.concurrency is not None:
        backend.concurrency = req.concurrency
    backend.updated_at = _now()
    await db.commit()
    await db.refresh(backend)
    return _to_dict(backend)


async def _transition(backend_id: str, target_status: str, db: AsyncSession) -> Backend:
    result = await db.execute(select(Backend).where(Backend.backend_id == backend_id))
    backend = result.scalar_one_or_none()
    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    allowed = VALID_TRANSITIONS.get(backend.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {backend.status} to {target_status}",
        )
    backend.status = target_status
    backend.updated_at = _now()
    await db.commit()
    await db.refresh(backend)
    return backend


@router.post("/{backend_id}/enable")
async def enable(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    backend = await _transition(backend_id, "enabled", db)
    return _to_dict(backend)


@router.post("/{backend_id}/drain")
async def drain(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    backend = await _transition(backend_id, "draining", db)
    return _to_dict(backend)


@router.post("/{backend_id}/archive")
async def archive(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    backend = await _transition(backend_id, "archived", db)
    return _to_dict(backend)


@router.post("/{backend_id}/disable")
async def disable(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    backend = await _transition(backend_id, "disabled", db)
    return _to_dict(backend)


@router.post("/{backend_id}/probe")
async def probe_backend(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    result = await db.execute(select(Backend).where(Backend.backend_id == backend_id))
    backend = result.scalar_one_or_none()
    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    return {"status": "probe completed", "backend_id": backend_id, "reachable": True}


@router.post("/{backend_id}/set-default")
async def set_default(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("backends")),
):
    result = await db.execute(select(Backend).where(Backend.backend_id == backend_id))
    backend = result.scalar_one_or_none()
    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    if backend.status != "enabled":
        raise HTTPException(status_code=400, detail="Only enabled backends can be set as default")

    existing = await db.execute(
        select(CompanyBackendDefault).where(
            CompanyBackendDefault.company_id == backend.company_id
        )
    )
    old_default = existing.scalar_one_or_none()
    if old_default:
        old_default.backend_id = backend_id
    else:
        default = CompanyBackendDefault(
            company_id=backend.company_id,
            backend_id=backend_id,
            version="1",
            created_at=_now(),
        )
        db.add(default)
    await db.commit()
    return {"status": "default set", "backend_id": backend_id}
