"""Release management router."""

import hashlib
import json as _json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.api.errors import raise_problem
from ibreeze_backend.catalog.models import (
    AgentCatalog,
    AgentModelBinding,
    ModelCatalog,
    ProviderCatalog,
    ProviderModelBinding,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.catalog_release import CatalogRelease, CatalogReleaseItem
from ibreeze_backend.models.skill import Skill
from ibreeze_backend.models.user import User
from ibreeze_backend.observability.logging_config import get_logger
from ibreeze_backend.releases.bundle import cleanup_dangling_objects, upload_resource_bundles
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
    resource_type: str
    resource_id: str
    resource_version: str | None = None
    action: str = "disable"
    reason: str
    code: str


@public_router.get("/catalog/keys")
async def get_catalog_keys_endpoint() -> dict[str, object]:
    return get_signed_keyset(Path(settings.catalog_key_dir))


async def _next_release_sequence(db: AsyncSession) -> int:
    result = await db.execute(select(CatalogRelease).order_by(CatalogRelease.release_sequence.desc()).limit(1))
    latest = result.scalar_one_or_none()
    if not latest:
        return 1
    return latest.release_sequence + 1


@admin_router.get("/catalog/releases")
async def list_releases_admin_endpoint(
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info("list_releases")
    result = await db.execute(
        select(CatalogRelease).order_by(CatalogRelease.release_sequence.desc()).limit(100)
    )
    releases = result.scalars().all()
    return {
        "data": [
            {
                "id": str(r.id),
                "version": r.minimum_client_version,
                "release_sequence": r.release_sequence,
                "signature": r.signature,
                "signing_key_id": r.signing_key_id,
                "status": r.status,
                "manifest": r.manifest_json or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in releases
        ]
    }


@admin_router.post(
    "/catalog/releases",
    status_code=status.HTTP_201_CREATED,
)
async def create_release_endpoint(
    body: ReleaseCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info("create_release", extra={"version": body.version, "notes": body.notes})
    sequence = await _next_release_sequence(db)

    release = CatalogRelease(
        release_sequence=sequence,
        minimum_client_version=body.version,
        manifest_object_key="",
        manifest_sha256="",
        signature="",
        signing_key_id="",
        status="publishing",
        created_by=current_user.id,
        created_at=datetime.now(UTC),
        manifest_json=None,
    )
    db.add(release)
    await db.flush()

    key_dir = Path(settings.catalog_key_dir)
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Unexpected private key type - expected Ed25519")

    manifest = await build_manifest(db, release.id, sequence, body.version, release.created_at)
    manifest_bytes = manifest_to_bytes(manifest)
    signature = compute_manifest_signature(manifest_bytes, private_key)

    manifest["signing_key_id"] = kid
    manifest["signature"] = signature

    # Re-serialize with signature included
    manifest_bytes = manifest_to_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    release.manifest_sha256 = manifest_sha
    release.signature = signature
    release.signing_key_id = kid
    release.manifest_json = manifest

    resource_type_map = {
        "agent": "agent_revision",
        "model": "model",
        "provider": "provider",
        "skill": "skill_revision",
    }

    for resource in manifest.get("resources", []):
        resource_type = resource_type_map.get(resource.get("type", ""))
        if resource_type is None:
            continue
        try:
            resource_id = uuid.UUID(resource["id"])
        except (KeyError, ValueError):
            continue
        db.add(CatalogReleaseItem(
            release_id=release.id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version_id=resource_id,
            content_sha256=resource.get("object_sha256", ""),
        ))

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
    _current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info("publish_release", extra={"release_id": str(release_id)})
    result = await db.execute(select(CatalogRelease).where(CatalogRelease.id == release_id))
    release = result.scalar_one_or_none()
    if not release:
        logger.warning("publish_release_failed", extra={"reason": "not_found", "release_id": str(release_id)})
        raise_problem(404, "RELEASE_NOT_FOUND", "Release not found")
        return {}
    if release.status == "published":
        logger.warning("publish_release_failed", extra={"reason": "already_published", "release_id": str(release_id)})
        raise_problem(400, "RELEASE_ALREADY_PUBLISHED", "Release already published")
        return {}

    if not release.manifest_json:
        raise_problem(400, "RELEASE_NOT_READY", "Release manifest not built")
        return {}

    manifest = release.manifest_json
    resources = manifest.get("resources", [])
    key_dir = Path(settings.catalog_key_dir)
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Unexpected private key type - expected Ed25519")

    manifest_key = f"catalog/releases/{release.release_sequence}/manifest.json"

    manifest_bytes = manifest_to_bytes(manifest)
    signature = compute_manifest_signature(manifest_bytes, private_key)

    manifest["signature"] = signature
    manifest_bytes = manifest_to_bytes(manifest)

    try:
        upload_resource_bundles(resources, manifest_bytes, manifest_key)
    except Exception as exc:
        logger.warning("publish_release_upload_failed", extra={"error": str(exc)})

    release.manifest_object_key = manifest_key
    release.status = "published"
    release.published_at = datetime.now(UTC)
    release.manifest_json = manifest
    await db.flush()

    logger.info("publish_release_success", extra={"release_id": str(release.id), "published_at": release.published_at})
    return {
        "id": str(release.id),
        "version": release.minimum_client_version,
        "status": release.status,
        "published_at": release.published_at,
        "manifest_object_key": manifest_key,
    }


@admin_router.post(
    "/emergency-disables",
    status_code=status.HTTP_201_CREATED,
)
async def create_emergency_disable_endpoint(
    body: EmergencyDisableCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info(
        "create_emergency_disable",
        extra={"resource_type": body.resource_type, "resource_id": body.resource_id, "actor": current_user.id},
    )

    payload = body.model_dump()
    payload_bytes = _json.dumps(payload, sort_keys=True).encode()
    payload_sha = hashlib.sha256(payload_bytes).hexdigest()

    key_dir = Path(settings.catalog_key_dir)
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Unexpected private key type - expected Ed25519")
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
        extra={
            "disable_id": str(disable.id),
            "sequence": disable.sequence,
            "resource_type": body.resource_type,
            "resource_id": body.resource_id,
        },
    )
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "resource_type": body.resource_type,
        "resource_id": body.resource_id,
        "reason": body.reason,
        "created_at": disable.created_at,
    }


@admin_router.get("/emergency-disables/latest")
async def get_latest_emergency_disable_endpoint(
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info("get_latest_emergency_disable")
    disable = await get_latest_emergency_disable(db)
    if not disable:
        logger.warning("get_latest_emergency_disable_failed", extra={"reason": "not_found"})
        raise_problem(404, "EMERGENCY_DISABLE_NOT_FOUND", "No emergency disables found")
        return {}
    payload = disable.payload_json or {}
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "resource_type": payload.get("resource_type", ""),
        "resource_id": payload.get("resource_id", ""),
        "reason": payload.get("reason", ""),
        "created_at": disable.created_at,
    }


@public_router.get("/catalog/manifest")
async def get_latest_manifest_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
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
        return {}
    if not release.manifest_json:
        logger.warning("get_latest_manifest_failed", extra={"reason": "no_stored_manifest"})
        raise_problem(404, "MANIFEST_NOT_FOUND", "Stored manifest not found")
        return {}
    return release.manifest_json


@public_router.get("/catalog/releases/{release_id}")
async def get_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    logger.info("get_release", extra={"release_id": str(release_id)})
    result = await db.execute(select(CatalogRelease).where(CatalogRelease.id == release_id))
    release = result.scalar_one_or_none()
    if not release:
        logger.warning("get_release_failed", extra={"reason": "not_found", "release_id": str(release_id)})
        raise_problem(404, "RELEASE_NOT_FOUND", "Release not found")
        return {}
    return {
        "id": str(release.id),
        "version": release.minimum_client_version,
        "manifest_object_key": release.manifest_object_key,
        "status": release.status,
        "release_sequence": release.release_sequence,
        "signing_key_id": release.signing_key_id,
        "published_at": release.published_at,
    }


@admin_router.post("/catalog/releases/{release_id}/reconcile")
async def reconcile_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info("reconcile_release", extra={"release_id": str(release_id)})
    result = await db.execute(select(CatalogRelease).where(CatalogRelease.id == release_id))
    release = result.scalar_one_or_none()
    if not release:
        raise_problem(404, "RELEASE_NOT_FOUND", "Release not found")
        return {}
    if not release.manifest_json:
        raise_problem(400, "RELEASE_NOT_READY", "Release manifest not built")
        return {}

    manifest_data = release.manifest_json
    resources = manifest_data.get("resources", [])
    manifest_key = release.manifest_object_key or f"catalog/releases/{release.release_sequence}/manifest.json"

    deleted = cleanup_dangling_objects(resources, manifest_key)
    logger.info("reconcile_release_completed", extra={"release_id": str(release_id), "deleted": deleted})
    return {"release_id": str(release_id), "dangling_deleted": deleted}


# 公开目录查询端点


@public_router.get("/catalog/agents")
async def list_agents_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """列出所有已发布的 Agent"""
    logger.info("list_agents")

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
) -> dict[str, object]:
    """列出指定 Agent 可用的模型"""
    logger.info("list_agent_models", extra={"agent_id": str(agent_id)})

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
        return {}

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
                    "binding_id": str(binding.id),
                    "id": str(model.id),
                    "model_id": str(model.id),
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
) -> dict[str, object]:
    """列出所有已发布的 Provider"""
    logger.info("list_providers")

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
) -> dict[str, object]:
    """列出指定 Provider 可用的模型"""
    logger.info("list_provider_models", extra={"provider_id": str(provider_id)})

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
        return {}

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
                    "binding_id": str(binding.id),
                    "id": str(model.id),
                    "model_id": str(model.id),
                    "provider_key": model.provider_key,
                    "model_key": model.model_key,
                    "display_name": model.display_name,
                    "context_window": model.context_window,
                    "supports_tools": model.supports_tools,
                    "supports_streaming": model.supports_streaming,
                    "supports_vision": model.supports_vision,
                    "provider_model_name": binding.provider_model_name,
                    "request_defaults": binding.request_defaults,
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
) -> dict[str, object]:
    """列出所有已发布的 Skill"""
    logger.info("list_skills")

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
) -> dict[str, object]:
    """获取指定 catalog release 中特定类型的资源"""
    logger.info(
        "get_release_resources",
        extra={"release_id": str(release_id), "resource_type": resource_type},
    )

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
) -> dict[str, object]:
    """获取最新紧急禁用"""
    logger.info("get_latest_emergency_disable_public")
    disable = await get_latest_emergency_disable(db)
    if not disable:
        logger.warning("get_latest_emergency_disable_public_failed", extra={"reason": "not_found"})
        raise_problem(404, "EMERGENCY_DISABLE_NOT_FOUND", "No emergency disables found")
        return {}
    payload = disable.payload_json or {}
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "resource_type": payload.get("resource_type", ""),
        "resource_id": payload.get("resource_id", ""),
        "reason": payload.get("reason", ""),
        "created_at": disable.created_at,
    }
