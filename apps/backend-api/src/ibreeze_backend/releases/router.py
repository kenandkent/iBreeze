"""Release management router."""

import hashlib
import json as _json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.api.errors import raise_problem
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.catalog_release import CatalogRelease
from ibreeze_backend.observability.logging_config import get_logger
from ibreeze_backend.releases.emergency import (
    create_emergency_disable,
    get_latest_emergency_disable,
)
from ibreeze_backend.releases.manifest import (
    build_manifest,
    compute_manifest_signature,
    manifest_to_bytes,
)
from ibreeze_backend.security.keys import get_signed_keyset, load_or_create_signing_keys
from ibreeze_backend.settings import settings

logger = get_logger("ibreeze.releases")

admin_router = APIRouter(prefix="/admin/api/v1", tags=["admin-releases"])
public_router = APIRouter(prefix="/api/v1", tags=["releases"])


class ReleaseCreate(BaseModel):
    version: str
    notes: str | None = None


class EmergencyDisableCreate(BaseModel):
    skill_ids: list[str]


@public_router.get("/catalog/keys")
async def get_catalog_keys_endpoint() -> dict[str, object]:
    return get_signed_keyset(Path(settings.catalog_key_dir))


async def _next_release_sequence(db: AsyncSession) -> int:
    result = await db.execute(select(CatalogRelease).order_by(CatalogRelease.release_sequence.desc()).limit(1))
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
    current_user=Depends(get_current_user),
) -> dict:
    logger.info("create_release", extra={"version": body.version, "notes": body.notes})
    sequence = await _next_release_sequence(db)
    manifest = await build_manifest(db, sequence)

    key_dir = Path(settings.catalog_key_dir)
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    private_key = serialization.load_pem_private_key(private_pem, password=None)

    manifest_bytes = manifest_to_bytes(manifest)
    signature = compute_manifest_signature(manifest_bytes, private_key)

    manifest["signing_key_id"] = kid
    manifest["signature"] = signature

    release = CatalogRelease(
        release_sequence=sequence,
        minimum_client_version=body.version,
        manifest_object_key="",
        manifest_sha256="",
        signature=signature,
        signing_key_id=kid,
        status="publishing",
        created_by=current_user.id,
        created_at=datetime.now(UTC),
    )
    db.add(release)
    await db.flush()

    logger.info(
        "create_release_success",
        extra={"release_id": str(release.id), "sequence": release.release_sequence, "version": body.version},
    )
    return {
        "id": str(release.id),
        "version": body.version,
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
    logger.info("publish_release", extra={"release_id": str(release_id)})
    result = await db.execute(select(CatalogRelease).where(CatalogRelease.id == release_id))
    release = result.scalar_one_or_none()
    if not release:
        logger.warning("publish_release_failed", extra={"reason": "not_found", "release_id": str(release_id)})
        raise_problem(404, "RELEASE_NOT_FOUND", "Release not found")
    if release.status == "published":
        logger.warning("publish_release_failed", extra={"reason": "already_published", "release_id": str(release_id)})
        raise_problem(400, "RELEASE_ALREADY_PUBLISHED", "Release already published")

    release.status = "published"
    release.published_at = datetime.now(UTC)
    await db.flush()

    logger.info("publish_release_success", extra={"release_id": str(release.id), "published_at": release.published_at})
    return {
        "id": str(release.id),
        "version": release.minimum_client_version,
        "status": release.status,
        "published_at": release.published_at,
    }


@admin_router.post(
    "/emergency-disables",
    status_code=status.HTTP_201_CREATED,
)
async def create_emergency_disable_endpoint(
    body: EmergencyDisableCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> dict:
    logger.info("create_emergency_disable", extra={"skill_ids": body.skill_ids, "actor": current_user.id})

    payload = {"skill_ids": body.skill_ids}
    payload_bytes = _json.dumps(payload, sort_keys=True).encode()
    payload_sha = hashlib.sha256(payload_bytes).hexdigest()

    key_dir = Path(settings.catalog_key_dir)
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    signature = compute_manifest_signature(payload_bytes, private_key)

    disable = await create_emergency_disable(
        db,
        actor_user_id=current_user.id,
        payload_json=payload,
        payload_sha256=payload_sha,
        signature=signature,
        signing_key_id=kid,
    )

    await db.flush()
    logger.info(
        "create_emergency_disable_success",
        extra={"disable_id": str(disable.id), "sequence": disable.sequence, "skill_ids": body.skill_ids},
    )
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": body.skill_ids,
        "created_at": disable.created_at,
    }


@admin_router.get("/emergency-disables/latest")
async def get_latest_emergency_disable_endpoint(
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    logger.info("get_latest_emergency_disable")
    disable = await get_latest_emergency_disable(db)
    if not disable:
        logger.warning("get_latest_emergency_disable_failed", extra={"reason": "not_found"})
        raise_problem(404, "EMERGENCY_DISABLE_NOT_FOUND", "No emergency disables found")
    skill_ids = disable.payload_json.get("skill_ids", []) if disable.payload_json else []
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": skill_ids,
        "created_at": disable.created_at,
    }


@public_router.get("/catalog/manifest")
async def get_latest_manifest_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    logger.info("get_latest_manifest")
    result = await db.execute(
        select(CatalogRelease)
        .where(CatalogRelease.status == "published")
        .order_by(CatalogRelease.release_sequence.desc())
        .limit(1)
    )
    release = result.scalar_one_or_none()
    if not release:
        logger.warning("get_latest_manifest_failed", extra={"reason": "no_published_release"})
        raise_problem(404, "RELEASE_NOT_FOUND", "No published release found")
    manifest = await build_manifest(db, release.release_sequence)
    return manifest


@public_router.get("/catalog/releases/{release_id}")
async def get_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    logger.info("get_release", extra={"release_id": str(release_id)})
    result = await db.execute(select(CatalogRelease).where(CatalogRelease.id == release_id))
    release = result.scalar_one_or_none()
    if not release:
        logger.warning("get_release_failed", extra={"reason": "not_found", "release_id": str(release_id)})
        raise_problem(404, "RELEASE_NOT_FOUND", "Release not found")
    return {
        "id": str(release.id),
        "version": release.minimum_client_version,
        "manifest_object_key": release.manifest_object_key,
        "status": release.status,
        "release_sequence": release.release_sequence,
        "signing_key_id": release.signing_key_id,
        "published_at": release.published_at,
    }


# 公开目录查询端点


@public_router.get("/catalog/agents")
async def list_agents_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出所有已发布的 Agent"""
    logger.info("list_agents")
    from ibreeze_backend.catalog.models import AgentCatalog

    result = await db.execute(select(AgentCatalog).where(AgentCatalog.status == "published"))
    agents = result.scalars().all()

    logger.info("list_agents_success", extra={"total": len(agents)})
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
    logger.info("list_agent_models", extra={"agent_id": str(agent_id)})
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
        logger.warning("list_agent_models_failed", extra={"reason": "agent_not_found", "agent_id": str(agent_id)})
        raise_problem(404, "AGENT_NOT_FOUND", "Agent not found")

    # 获取绑定的模型
    binding_result = await db.execute(select(AgentModelBinding).where(AgentModelBinding.agent_id == agent_id))
    bindings = binding_result.scalars().all()

    models = []
    for binding in bindings:
        model_result = await db.execute(select(ModelCatalog).where(ModelCatalog.id == binding.model_id))
        model = model_result.scalar_one_or_none()
        if model and model.status == "published":
            models.append(
                {
                    "id": str(model.id),
                    "provider_key": model.provider_key,
                    "model_key": model.model_key,
                    "display_name": model.display_name,
                    "context_window": model.context_window,
                    "supports_tools": model.supports_tools,
                    "supports_streaming": model.supports_streaming,
                    "supports_vision": model.supports_vision,
                }
            )

    logger.info("list_agent_models_success", extra={"agent_id": str(agent_id), "total": len(models)})
    return {
        "data": models,
        "meta": {"total": len(models)},
    }


@public_router.get("/catalog/providers")
async def list_providers_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出所有已发布的 Provider"""
    logger.info("list_providers")
    from ibreeze_backend.catalog.models import ProviderCatalog

    result = await db.execute(select(ProviderCatalog).where(ProviderCatalog.status == "published"))
    providers = result.scalars().all()

    logger.info("list_providers_success", extra={"total": len(providers)})
    return {
        "data": [
            {
                "id": str(provider.id),
                "key": provider.key,
                "display_name": provider.display_name,
                "base_url": provider.base_url,
                "protocol": provider.protocol,
                "auth_scheme": provider.auth_scheme,
                "catalog_revision": provider.catalog_revision,
                "status": provider.status,
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
    logger.info("list_provider_models", extra={"provider_id": str(provider_id)})
    from ibreeze_backend.catalog.models import ModelCatalog, ProviderCatalog, ProviderModelBinding

    # 验证 Provider 存在且已发布
    provider_result = await db.execute(
        select(ProviderCatalog).where(
            ProviderCatalog.id == provider_id,
            ProviderCatalog.status == "published",
        )
    )
    provider = provider_result.scalar_one_or_none()
    if not provider:
        logger.warning(
            "list_provider_models_failed", extra={"reason": "provider_not_found", "provider_id": str(provider_id)}
        )
        raise_problem(404, "PROVIDER_NOT_FOUND", "Provider not found")

    # 获取绑定的模型
    binding_result = await db.execute(
        select(ProviderModelBinding).where(ProviderModelBinding.provider_id == provider_id)
    )
    bindings = binding_result.scalars().all()

    models = []
    for binding in bindings:
        model_result = await db.execute(select(ModelCatalog).where(ModelCatalog.id == binding.model_id))
        model = model_result.scalar_one_or_none()
        if model and model.status == "published":
            models.append(
                {
                    "id": str(model.id),
                    "provider_key": model.provider_key,
                    "model_key": model.model_key,
                    "display_name": model.display_name,
                    "context_window": model.context_window,
                    "supports_tools": model.supports_tools,
                    "supports_streaming": model.supports_streaming,
                    "supports_vision": model.supports_vision,
                }
            )

    logger.info("list_provider_models_success", extra={"provider_id": str(provider_id), "total": len(models)})
    return {
        "data": models,
        "meta": {"total": len(models)},
    }


@public_router.get("/catalog/skills")
async def list_skills_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """列出所有已发布的 Skill"""
    logger.info("list_skills")
    from ibreeze_backend.models.skill import Skill

    result = await db.execute(select(Skill).where(Skill.status == "published"))
    skills = result.scalars().all()

    logger.info("list_skills_success", extra={"total": len(skills)})
    return {
        "data": [
            {
                "id": str(skill.id),
                "key": skill.key,
                "display_name": skill.display_name,
                "description": skill.description,
                "catalog_revision": skill.catalog_revision,
                "status": skill.status,
            }
            for skill in skills
        ],
        "meta": {"total": len(skills)},
    }


@public_router.get("/catalog/releases/{release_id}/resources/{resource_type}")
async def get_release_resources(
    release_id: uuid.UUID,
    resource_type: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取指定 catalog release 中特定类型的资源"""
    logger.info(
        "get_release_resources",
        extra={"release_id": str(release_id), "resource_type": resource_type},
    )
    from ibreeze_backend.models.catalog_release import CatalogReleaseItem

    result = await db.execute(
        select(CatalogReleaseItem).where(
            CatalogReleaseItem.release_id == release_id,
            CatalogReleaseItem.resource_type == resource_type,
        )
    )
    items = result.scalars().all()

    logger.info(
        "get_release_resources_success",
        extra={"release_id": str(release_id), "resource_type": resource_type, "total": len(items)},
    )
    return {
        "data": [
            {
                "release_id": str(item.release_id),
                "resource_type": item.resource_type,
                "resource_id": str(item.resource_id),
                "resource_version_id": str(item.resource_version_id),
                "content_sha256": item.content_sha256,
            }
            for item in items
        ],
        "meta": {"total": len(items)},
    }


@public_router.get("/catalog/emergency-disables/latest")
async def get_latest_emergency_disable_public_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取最新紧急禁用"""
    logger.info("get_latest_emergency_disable_public")
    disable = await get_latest_emergency_disable(db)
    if not disable:
        logger.warning("get_latest_emergency_disable_public_failed", extra={"reason": "not_found"})
        raise_problem(404, "EMERGENCY_DISABLE_NOT_FOUND", "No emergency disables found")
    skill_ids = disable.payload_json.get("skill_ids", []) if disable.payload_json else []
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": skill_ids,
        "created_at": disable.created_at,
    }
