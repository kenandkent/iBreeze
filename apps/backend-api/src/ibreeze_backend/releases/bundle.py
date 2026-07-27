"""Resource bundling and S3 upload for immutable catalog releases."""

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import AgentCatalog, ModelCatalog, ProviderCatalog
from ibreeze_backend.models.skill import Skill, SkillVersion
from ibreeze_backend.observability.logging_config import get_logger
from ibreeze_backend.releases.canonical_json import canonical_bytes
from ibreeze_backend.settings import settings

logger = get_logger("ibreeze.releases.bundle")

S3_CLIENT_CACHE: dict[str, Any] = {}


def _get_s3_client() -> Any:
    if "client" not in S3_CLIENT_CACHE:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        S3_CLIENT_CACHE["client"] = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return S3_CLIENT_CACHE["client"]


def _object_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _freeze_resource(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = canonical_bytes(payload)
    return {
        "object_key": "",
        "object_sha256": _object_sha256(serialized),
        "size": len(serialized),
    }


def _resource_object_key(resource_type: str, resource_id: uuid.UUID, sequence: int) -> str:
    return f"catalog/releases/{sequence}/{resource_type}s/{resource_id}.json"


def _freeze_agent(agent: AgentCatalog, sequence: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": agent.key,
        "display_name": agent.display_name,
        "description": agent.description,
        "catalog_revision": agent.catalog_revision,
        "version": agent.version,
    }
    bundle = _freeze_resource(payload)
    bundle["object_key"] = _resource_object_key("agent", agent.id, sequence)
    return {
        "type": "agent",
        "id": str(agent.id),
        "key": agent.key,
        "catalog_revision": agent.catalog_revision,
        "display_name": agent.display_name,
        "version": agent.version,
        "object_key": bundle["object_key"],
        "object_sha256": bundle["object_sha256"],
        "size": bundle["size"],
    }


def _freeze_model(model: ModelCatalog, sequence: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider_key": model.provider_key,
        "model_key": model.model_key,
        "display_name": model.display_name,
        "context_window": model.context_window,
        "max_output_tokens": model.max_output_tokens,
        "catalog_revision": model.catalog_revision,
        "version": model.version,
        "supports_tools": model.supports_tools,
        "supports_streaming": model.supports_streaming,
        "supports_vision": model.supports_vision,
    }
    bundle = _freeze_resource(payload)
    bundle["object_key"] = _resource_object_key("model", model.id, sequence)
    return {
        "type": "model",
        "id": str(model.id),
        "key": f"{model.provider_key}/{model.model_key}",
        "catalog_revision": model.catalog_revision,
        "display_name": model.display_name,
        "version": model.version,
        "object_key": bundle["object_key"],
        "object_sha256": bundle["object_sha256"],
        "size": bundle["size"],
    }


def _freeze_provider(provider: ProviderCatalog, sequence: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": provider.key,
        "display_name": provider.display_name,
        "protocol": provider.protocol,
        "base_url": provider.base_url,
        "auth_scheme": provider.auth_scheme,
        "catalog_revision": provider.catalog_revision,
        "version": provider.version,
    }
    bundle = _freeze_resource(payload)
    bundle["object_key"] = _resource_object_key("provider", provider.id, sequence)
    return {
        "type": "provider",
        "id": str(provider.id),
        "key": provider.key,
        "catalog_revision": provider.catalog_revision,
        "display_name": provider.display_name,
        "version": provider.version,
        "object_key": bundle["object_key"],
        "object_sha256": bundle["object_sha256"],
        "size": bundle["size"],
    }


def _freeze_skill(skill: Skill, version: SkillVersion | None, sequence: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": skill.key,
        "display_name": skill.display_name,
        "description": skill.description,
        "catalog_revision": skill.catalog_revision,
        "version": skill.version,
    }
    bundle = _freeze_resource(payload)
    bundle["object_key"] = _resource_object_key("skill", skill.id, sequence)
    entry: dict[str, Any] = {
        "type": "skill",
        "id": str(skill.id),
        "key": skill.key,
        "catalog_revision": skill.catalog_revision,
        "display_name": skill.display_name,
        "version": skill.version,
        "object_key": bundle["object_key"],
        "object_sha256": bundle["object_sha256"],
        "size": bundle["size"],
    }
    if version:
        entry["content_sha256"] = version.content_sha256
        entry["skill_version_id"] = str(version.id)
        entry["skill_version"] = version.version
    return entry


async def freeze_resources(db: AsyncSession, release_id: uuid.UUID, sequence: int) -> list[dict[str, Any]]:
    logger.info("freeze_resources.start", extra={"release_id": str(release_id), "sequence": sequence})
    resources: list[dict[str, Any]] = []

    agents_result = await db.execute(select(AgentCatalog).where(AgentCatalog.status == "published"))
    for agent in agents_result.scalars().all():
        resources.append(_freeze_agent(agent, sequence))

    models_result = await db.execute(select(ModelCatalog).where(ModelCatalog.status == "published"))
    for model in models_result.scalars().all():
        resources.append(_freeze_model(model, sequence))

    providers_result = await db.execute(select(ProviderCatalog).where(ProviderCatalog.status == "published"))
    for provider in providers_result.scalars().all():
        resources.append(_freeze_provider(provider, sequence))

    skills_result = await db.execute(select(Skill).where(Skill.status == "published"))
    for skill in skills_result.scalars().all():
        version_result = await db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill.id)
            .order_by(SkillVersion.created_at.desc())
            .limit(1)
        )
        latest_version = version_result.scalar_one_or_none()
        resources.append(_freeze_skill(skill, latest_version, sequence))

    logger.info("freeze_resources.completed", extra={"release_id": str(release_id), "count": len(resources)})
    return resources


def upload_resource_bundles(resources: list[dict[str, Any]], manifest_bytes: bytes, manifest_key: str) -> list[str]:
    client = _get_s3_client()
    bucket = settings.s3_bucket_name
    uploaded: list[str] = []

    for resource in resources:
        object_key: str = resource["object_key"]
        if not object_key:
            continue
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=canonical_bytes(resource),
            ContentType="application/json",
        )
        uploaded.append(object_key)

    client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=manifest_bytes,
        ContentType="application/json",
    )
    uploaded.append(manifest_key)

    logger.info("upload_resource_bundles.completed", extra={"count": len(uploaded)})
    return uploaded


def list_dangling_objects(resources: list[dict[str, Any]], manifest_key: str) -> list[str]:
    client = _get_s3_client()
    bucket = settings.s3_bucket_name
    expected_keys: set[str] = {r["object_key"] for r in resources if r.get("object_key")}
    expected_keys.add(manifest_key)

    dangling: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="catalog/releases/"):
        for obj in page.get("Contents", []):
            key: str = obj["Key"]
            if key not in expected_keys:
                dangling.append(key)
    return dangling


def cleanup_dangling_objects(resources: list[dict[str, Any]], manifest_key: str) -> int:
    dangling = list_dangling_objects(resources, manifest_key)
    if not dangling:
        return 0
    client = _get_s3_client()
    bucket = settings.s3_bucket_name
    client.delete_objects(
        Bucket=bucket,
        Delete={"Objects": [{"Key": k} for k in dangling]},
    )
    logger.info("cleanup_dangling_objects.completed", extra={"deleted": len(dangling)})
    return len(dangling)
