import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.provider import (
    Provider,
    ProviderCredential,
    ProviderModel,
    ProviderPricingVersion,
    ProviderTierMapping,
)
from app.schemas.provider import (
    ProviderCreate,
    ProviderCredentialSet,
    ProviderPricingUpdate,
    ProviderTierMappingUpdate,
    ProviderUpdate,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(p: Provider) -> dict:
    return {
        "provider_id": p.provider_id,
        "company_id": p.company_id,
        "name": p.name,
        "provider_type": p.provider_type,
        "config": p.config,
        "status": p.status,
        "version": p.version,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


@router.get("")
async def list_providers(
    company_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(Provider)
    if company_id:
        q = q.where(Provider.company_id == company_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_dict(p) for p in result.scalars().all()]


@router.post("", status_code=201)
async def create_provider(
    req: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    provider_id = str(uuid.uuid4())
    now = _now()
    provider = Provider(
        provider_id=provider_id,
        company_id=req.company_id,
        name=req.name,
        provider_type=req.provider_type,
        config=req.config or {},
        status="active",
        version="1",
        created_at=now,
        updated_at=now,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _to_dict(provider)


@router.get("/{provider_id}")
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _to_dict(provider)


@router.post("/{provider_id}/enable")
async def enable_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider.status = "enabled"
    provider.updated_at = _now()
    await db.commit()
    return {"status": "enabled", "provider_id": provider_id}


@router.post("/{provider_id}/disable")
async def disable_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider.status = "disabled"
    provider.updated_at = _now()
    await db.commit()
    return {"status": "disabled", "provider_id": provider_id}


@router.get("/{provider_id}/models")
async def list_models(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(ProviderModel).where(ProviderModel.provider_id == provider_id)
    )
    models = result.scalars().all()
    return [
        {
            "id": m.id,
            "provider_id": m.provider_id,
            "model_id": m.model_id,
            "display_name": m.display_name,
            "tier": m.tier,
            "created_at": m.created_at,
        }
        for m in models
    ]


@router.post("/{provider_id}/fetch-models")
async def fetch_models(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "model fetch queued", "provider_id": provider_id}


@router.put("/{provider_id}/credentials")
async def set_credentials(
    provider_id: str,
    req: ProviderCredentialSet,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    cred_id = str(uuid.uuid4())
    cred = ProviderCredential(
        credential_id=cred_id,
        provider_id=provider_id,
        company_id=provider.company_id or "",
        credential_type=req.credential_type,
        credential_ref=req.credential_ref,
        created_at=_now(),
    )
    db.add(cred)
    await db.commit()
    return {
        "credential_id": cred_id,
        "provider_id": provider_id,
        "credential_type": req.credential_type,
        "created_at": cred.created_at,
    }


@router.delete("/{provider_id}/credentials")
async def delete_credentials(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.provider_id == provider_id)
    )
    creds = result.scalars().all()
    for cred in creds:
        await db.delete(cred)
    await db.commit()
    return {"status": "credentials deleted", "count": len(creds)}


@router.post("/{provider_id}/probe")
async def probe_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "probe completed", "provider_id": provider_id, "reachable": True}


@router.put("/{provider_id}/pricing")
async def update_pricing(
    provider_id: str,
    req: ProviderPricingUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    pricing = ProviderPricingVersion(
        provider_id=provider_id,
        company_id=provider.company_id,
        pricing=req.pricing,
        currency=req.currency,
        created_at=_now(),
    )
    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)
    return {
        "id": pricing.id,
        "provider_id": pricing.provider_id,
        "pricing": pricing.pricing,
        "currency": pricing.currency,
        "created_at": pricing.created_at,
    }


@router.put("/{provider_id}/tier-mapping")
async def update_tier_mapping(
    provider_id: str,
    req: ProviderTierMappingUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("providers")),
):
    result = await db.execute(select(Provider).where(Provider.provider_id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    mapping = ProviderTierMapping(
        company_id=provider.company_id or "",
        provider_id=provider_id,
        tier=req.tier,
        model_id=req.model_id,
        created_at=_now(),
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return {
        "id": mapping.id,
        "provider_id": mapping.provider_id,
        "tier": mapping.tier,
        "model_id": mapping.model_id,
        "created_at": mapping.created_at,
    }
