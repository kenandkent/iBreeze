"""Resource bundling and S3 upload for immutable catalog releases."""

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import (
    AgentCatalog,
    AgentVersionRange,
    ModelCatalog,
    ProviderCatalog,
    ProviderModelBinding,
)
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


def _finalize_resource(entry: dict[str, Any]) -> dict[str, Any]:
    """Digest exactly the canonical bytes that are uploaded for this entry."""
    body = dict(entry)
    body.pop("object_sha256", None)
    body.pop("size", None)
    serialized = canonical_bytes(body)
    entry["object_sha256"] = _object_sha256(serialized)
    entry["size"] = len(serialized)
    return entry


def _freeze_resource(entry: dict[str, Any]) -> dict[str, Any]:
    """Finalize an already assembled resource entry.

    This small primitive is kept public within the module so release tests and
    catalog extensions can verify the exact digest/size rule without having to
    construct a concrete Agent/Model/Provider ORM object.
    """
    body = dict(entry)
    body.setdefault("object_key", "")
    return _finalize_resource(body)


def _resource_object_key(resource_type: str, resource_id: uuid.UUID, sequence: int) -> str:
    return f"catalog/releases/{sequence}/{resource_type}s/{resource_id}.json"


def _freeze_agent(
    agent: AgentCatalog,
    sequence: int,
    version_ranges: list[AgentVersionRange] | None = None,
) -> dict[str, Any]:
    version_ranges = version_ranges or []
    payload: dict[str, Any] = {
        "key": agent.key,
        "display_name": agent.display_name,
        "description": agent.description,
        "catalog_revision": agent.catalog_revision,
        "version": agent.version,
        "version_ranges": [
            {
                "min_version": item.min_version,
                "max_version_exclusive": item.max_version_exclusive,
                "executable_names": item.executable_names,
                "supported_platforms": item.supported_platforms,
                "probe_argv": item.probe_argv,
                "network_domains": item.network_domains,
                "capability_tags": item.capability_tags,
                "adapter_contract_version": item.adapter_contract_version,
            }
            for item in version_ranges
        ],
    }
    entry = {
        "type": "agent",
        "id": str(agent.id),
        "key": agent.key,
        "catalog_revision": agent.catalog_revision,
        "display_name": agent.display_name,
        "version": agent.version,
        "object_key": _resource_object_key("agent", agent.id, sequence),
        "description": agent.description,
        "version_ranges": payload["version_ranges"],
        "network_domains": sorted(
            {
                domain
                for item in payload["version_ranges"]
                for domain in item["network_domains"]
            }
        ),
    }
    return _finalize_resource(entry)


def _freeze_model(model: ModelCatalog, sequence: int) -> dict[str, Any]:
    entry = {
        "type": "model",
        "id": str(model.id),
        "key": f"{model.provider_key}/{model.model_key}",
        "catalog_revision": model.catalog_revision,
        "display_name": model.display_name,
        "version": model.version,
        "object_key": _resource_object_key("model", model.id, sequence),
        "provider_key": model.provider_key,
        "model_key": model.model_key,
        "context_window": model.context_window,
        "max_output_tokens": model.max_output_tokens,
        "supports_tools": model.supports_tools,
        "supports_streaming": model.supports_streaming,
        "supports_vision": model.supports_vision,
    }
    return _finalize_resource(entry)


def _freeze_provider(
    provider: ProviderCatalog,
    sequence: int,
    model_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    model_bindings = model_bindings or []
    entry = {
        "type": "provider",
        "id": str(provider.id),
        "key": provider.key,
        "catalog_revision": provider.catalog_revision,
        "display_name": provider.display_name,
        "version": provider.version,
        "protocol": provider.protocol,
        "base_url": provider.base_url,
        "auth_scheme": provider.auth_scheme,
        "model_bindings": model_bindings,
        "object_key": _resource_object_key("provider", provider.id, sequence),
    }
    return _finalize_resource(entry)


def _freeze_skill(skill: Skill, version: SkillVersion | None, sequence: int) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "skill",
        "id": str(skill.id),
        "key": skill.key,
        "catalog_revision": skill.catalog_revision,
        "display_name": skill.display_name,
        "version": skill.version,
        "object_key": _resource_object_key("skill", skill.id, sequence),
        "description": skill.description,
    }
    if version:
        entry["content_sha256"] = version.content_sha256
        entry["skill_version_id"] = str(version.id)
        entry["skill_version"] = version.version
    return _finalize_resource(entry)


async def freeze_resources(db: AsyncSession, release_id: uuid.UUID, sequence: int) -> list[dict[str, Any]]:
    logger.info("freeze_resources.start", extra={"release_id": str(release_id), "sequence": sequence})
    resources: list[dict[str, Any]] = []

    agents_result = await db.execute(select(AgentCatalog).where(AgentCatalog.status == "published"))
    for agent in agents_result.scalars().all():
        ranges_result = await db.execute(
            select(AgentVersionRange).where(AgentVersionRange.agent_id == agent.id)
        )
        resources.append(_freeze_agent(agent, sequence, list(ranges_result.scalars().all())))

    models_result = await db.execute(select(ModelCatalog).where(ModelCatalog.status == "published"))
    for model in models_result.scalars().all():
        resources.append(_freeze_model(model, sequence))

    providers_result = await db.execute(select(ProviderCatalog).where(ProviderCatalog.status == "published"))
    for provider in providers_result.scalars().all():
        bindings_result = await db.execute(
            select(ProviderModelBinding).where(ProviderModelBinding.provider_id == provider.id)
        )
        model_bindings: list[dict[str, Any]] = []
        for binding in bindings_result.scalars().all():
            model_result = await db.execute(select(ModelCatalog).where(ModelCatalog.id == binding.model_id))
            model_catalog = model_result.scalar_one_or_none()
            if model_catalog is None or model_catalog.status != "published":
                continue
            model_bindings.append(
                {
                    "binding_id": str(binding.id),
                    "model_id": str(binding.model_id),
                    "provider_model_name": binding.provider_model_name,
                    "request_defaults": binding.request_defaults,
                }
            )
        resources.append(_freeze_provider(provider, sequence, model_bindings))

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
        body = dict(resource)
        object_sha256 = body.pop("object_sha256", None)
        size = body.pop("size", None)
        serialized = canonical_bytes(body)
        if object_sha256 != _object_sha256(serialized) or size != len(serialized):
            raise ValueError("CATALOG_RESOURCE_DIGEST_MISMATCH")
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=serialized,
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
