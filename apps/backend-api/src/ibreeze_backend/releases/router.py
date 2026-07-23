"""Release management router."""
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.catalog_release import CatalogRelease
from ibreeze_backend.releases.emergency import (
    create_emergency_disable,
    get_latest_emergency_disable,
)
from ibreeze_backend.releases.manifest import (
    build_manifest,
    compute_manifest_signature,
    manifest_to_bytes,
)
from ibreeze_backend.security.keys import load_or_create_signing_keys
from ibreeze_backend.settings import settings

admin_router = APIRouter(prefix="/admin/api/v1", tags=["admin-releases"])
public_router = APIRouter(prefix="/api/v1", tags=["releases"])


class ReleaseCreate(BaseModel):
    version: str
    notes: str | None = None


class EmergencyDisableCreate(BaseModel):
    skill_ids: list[str]


async def _next_release_sequence(db: AsyncSession) -> int:
    result = await db.execute(
        select(CatalogRelease).order_by(CatalogRelease.release_sequence.desc()).limit(1)
    )
    latest = result.scalar_one_or_none()
    if not latest:
        return 1
    return latest.release_sequence + 1


@admin_router.post(
    "/catalog/releases",
    status_code=status.HTTP_201_CREATED,
)
async def create_release_endpoint(
    body: ReleaseCreate,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    sequence = await _next_release_sequence(db)
    manifest = await build_manifest(db, sequence)

    key_dir = Path(settings.token_secret or "keys")
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    private_key = serialization.load_pem_private_key(private_pem, password=None)

    manifest_bytes = manifest_to_bytes(manifest)
    signature = compute_manifest_signature(manifest_bytes, private_key)

    manifest["signing_key_id"] = kid
    manifest["signature"] = signature

    release = CatalogRelease(
        version=body.version,
        manifest=manifest,
        notes=body.notes,
        release_sequence=sequence,
        signature=signature,
        signing_key_id=kid,
    )
    db.add(release)
    await db.flush()

    return {
        "id": str(release.id),
        "version": release.version,
        "release_sequence": release.release_sequence,
        "status": release.status,
        "signing_key_id": kid,
    }


@admin_router.post("/catalog/releases/{release_id}/publish")
async def publish_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(CatalogRelease).where(CatalogRelease.id == release_id)
    )
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    if release.status == "published":
        raise HTTPException(status_code=400, detail="Release already published")

    release.status = "published"
    release.published_at = datetime.now(UTC)
    await db.flush()

    return {
        "id": str(release.id),
        "version": release.version,
        "status": release.status,
        "published_at": release.published_at.isoformat(),
    }


@admin_router.post(
    "/emergency-disables",
    status_code=status.HTTP_201_CREATED,
)
async def create_emergency_disable_endpoint(
    body: EmergencyDisableCreate,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    disable = await create_emergency_disable(db, body.skill_ids)
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": disable.disabled_skill_ids,
        "created_at": disable.created_at.isoformat(),
    }


@admin_router.get("/emergency-disables/latest")
async def get_latest_emergency_disable_endpoint(
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    disable = await get_latest_emergency_disable(db)
    if not disable:
        raise HTTPException(status_code=404, detail="No emergency disables found")
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": disable.disabled_skill_ids,
        "created_at": disable.created_at.isoformat(),
    }


@public_router.get("/catalog/manifest")
async def get_latest_manifest_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(
        select(CatalogRelease)
        .where(CatalogRelease.status == "published")
        .order_by(CatalogRelease.release_sequence.desc())
        .limit(1)
    )
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="No published release found")
    return release.manifest


@public_router.get("/catalog/releases/{release_id}")
async def get_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(
        select(CatalogRelease).where(CatalogRelease.id == release_id)
    )
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    return {
        "id": str(release.id),
        "version": release.version,
        "manifest": release.manifest,
        "status": release.status,
        "notes": release.notes,
        "release_sequence": release.release_sequence,
        "signing_key_id": release.signing_key_id,
        "published_at": (
            release.published_at.isoformat() if release.published_at else None
        ),
    }


# 公开目录查询端点

@public_router.get("/catalog/agents")
async def list_agents_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出所有已发布的 Agent"""
    from ibreeze_backend.catalog.models import AgentCatalog
    
    result = await db.execute(
        select(AgentCatalog).where(AgentCatalog.status == "published")
    )
    agents = result.scalars().all()
    
    return {
        "data": [
            {
                "id": str(agent.id),
                "key": agent.key,
                "display_name": agent.display_name,
                "description": agent.description,
                "catalog_revision": agent.catalog_revision,
            }
            for agent in agents
        ],
        "meta": {"total": len(agents)},
    }


@public_router.get("/catalog/agents/{agent_id}/models")
async def list_agent_models_endpoint(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出指定 Agent 可用的模型"""
    from ibreeze_backend.catalog.models import AgentCatalog, AgentModelBinding, ModelCatalog
    
    # 验证 Agent 存在且已发布
    agent_result = await db.execute(
        select(AgentCatalog).where(
            AgentCatalog.id == agent_id,
            AgentCatalog.status == "published",
        )
    )
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # 获取绑定的模型
    binding_result = await db.execute(
        select(AgentModelBinding).where(AgentModelBinding.agent_id == agent_id)
    )
    bindings = binding_result.scalars().all()
    
    models = []
    for binding in bindings:
        model_result = await db.execute(
            select(ModelCatalog).where(ModelCatalog.id == binding.model_id)
        )
        model = model_result.scalar_one_or_none()
        if model and model.status == "published":
            models.append({
                "id": str(model.id),
                "provider_key": model.provider_key,
                "model_key": model.model_key,
                "display_name": model.display_name,
                "context_window": model.context_window,
                "supports_tools": model.supports_tools,
                "supports_streaming": model.supports_streaming,
                "supports_vision": model.supports_vision,
            })
    
    return {
        "data": models,
        "meta": {"total": len(models)},
    }


@public_router.get("/catalog/providers")
async def list_providers_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出所有已发布的 Provider"""
    from ibreeze_backend.models.catalog import ProviderCatalog
    
    result = await db.execute(
        select(ProviderCatalog).where(ProviderCatalog.status == "published")
    )
    providers = result.scalars().all()
    
    return {
        "data": [
            {
                "id": str(provider.id),
                "display_name": provider.display_name,
                "base_url": provider.base_url,
                "api_protocol": provider.api_protocol,
            }
            for provider in providers
        ],
        "meta": {"total": len(providers)},
    }


@public_router.get("/catalog/providers/{provider_id}/models")
async def list_provider_models_endpoint(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出指定 Provider 可用的模型"""
    from ibreeze_backend.catalog.models import ProviderCatalog, ProviderModelBinding, ModelCatalog
    
    # 验证 Provider 存在且已发布
    provider_result = await db.execute(
        select(ProviderCatalog).where(
            ProviderCatalog.id == provider_id,
            ProviderCatalog.status == "published",
        )
    )
    provider = provider_result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    # 获取绑定的模型
    binding_result = await db.execute(
        select(ProviderModelBinding).where(ProviderModelBinding.provider_id == provider_id)
    )
    bindings = binding_result.scalars().all()
    
    models = []
    for binding in bindings:
        model_result = await db.execute(
            select(ModelCatalog).where(ModelCatalog.id == binding.model_id)
        )
        model = model_result.scalar_one_or_none()
        if model and model.status == "published":
            models.append({
                "id": str(model.id),
                "provider_key": model.provider_key,
                "model_key": model.model_key,
                "display_name": model.display_name,
                "context_window": model.context_window,
                "supports_tools": model.supports_tools,
                "supports_streaming": model.supports_streaming,
                "supports_vision": model.supports_vision,
            })
    
    return {
        "data": models,
        "meta": {"total": len(models)},
    }


@public_router.get("/catalog/skills")
async def list_skills_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出所有已发布的 Skill"""
    from ibreeze_backend.models.skill import Skill
    
    result = await db.execute(
        select(Skill).where(Skill.is_active == True)
    )
    skills = result.scalars().all()
    
    return {
        "data": [
            {
                "id": str(skill.id),
                "name": skill.name,
                "version": skill.version,
                "category": skill.category,
                "description": skill.description,
                "compatibility": skill.compatibility,
            }
            for skill in skills
        ],
        "meta": {"total": len(skills)},
    }


@public_router.get("/catalog/emergency-disables/latest")
async def get_latest_emergency_disable_public_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取最新紧急禁用"""
    disable = await get_latest_emergency_disable(db)
    if not disable:
        raise HTTPException(status_code=404, detail="No emergency disables found")
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": disable.disabled_skill_ids,
        "created_at": disable.created_at.isoformat(),
    }
