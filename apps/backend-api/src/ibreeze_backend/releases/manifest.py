"""Manifest builder and signing for catalog releases."""

import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import AgentCatalog, ModelCatalog, ProviderCatalog
from ibreeze_backend.models.skill import Skill, SkillVersion
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.releases.manifest")


def _content_sha256(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


async def build_manifest(db: AsyncSession, sequence: int) -> dict:
    """Generate manifest from all published catalog resources with content hashes."""
    logger.info("build_manifest.start", extra={"sequence": sequence})

    resources: list[dict] = []

    agents_result = await db.execute(select(AgentCatalog).where(AgentCatalog.status == "published"))
    for agent in agents_result.scalars().all():
        resources.append({
            "type": "agent",
            "id": str(agent.id),
            "key": agent.key,
            "catalog_revision": agent.catalog_revision,
            "display_name": agent.display_name,
            "version": agent.version,
            "content_sha256": _content_sha256({
                "key": agent.key, "display_name": agent.display_name,
                "description": agent.description, "catalog_revision": agent.catalog_revision,
            }),
        })

    models_result = await db.execute(select(ModelCatalog).where(ModelCatalog.status == "published"))
    for model in models_result.scalars().all():
        resources.append({
            "type": "model",
            "id": str(model.id),
            "key": f"{model.provider_key}/{model.model_key}",
            "catalog_revision": model.catalog_revision,
            "display_name": model.display_name,
            "version": model.version,
            "content_sha256": _content_sha256({
                "provider_key": model.provider_key, "model_key": model.model_key,
                "display_name": model.display_name, "context_window": model.context_window,
                "max_output_tokens": model.max_output_tokens,
            }),
        })

    providers_result = await db.execute(select(ProviderCatalog).where(ProviderCatalog.status == "published"))
    for provider in providers_result.scalars().all():
        resources.append({
            "type": "provider",
            "id": str(provider.id),
            "key": provider.key,
            "catalog_revision": provider.catalog_revision,
            "display_name": provider.display_name,
            "version": provider.version,
            "content_sha256": _content_sha256({
                "key": provider.key, "display_name": provider.display_name,
                "protocol": provider.protocol, "base_url": provider.base_url,
                "auth_scheme": provider.auth_scheme,
            }),
        })

    skills_result = await db.execute(select(Skill).where(Skill.status == "published"))
    for skill in skills_result.scalars().all():
        version_result = await db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill.id)
            .order_by(SkillVersion.created_at.desc())
            .limit(1)
        )
        latest_version = version_result.scalar_one_or_none()
        content_sha256 = latest_version.content_sha256 if latest_version else ""
        resources.append({
            "type": "skill",
            "id": str(skill.id),
            "key": skill.key,
            "catalog_revision": skill.catalog_revision,
            "display_name": skill.display_name,
            "version": skill.version,
            "content_sha256": content_sha256,
        })

    manifest = {
        "release_sequence": sequence,
        "resources": resources,
    }
    logger.info("build_manifest.completed", extra={"sequence": sequence, "resource_count": len(resources)})
    return manifest


def compute_manifest_signature(manifest_bytes: bytes, private_key: Ed25519PrivateKey) -> str:
    """Sign manifest bytes with Ed25519 and return hex signature."""
    signature = private_key.sign(manifest_bytes)
    return signature.hex()


def manifest_to_bytes(manifest: dict) -> bytes:
    """Canonicalize manifest to deterministic bytes."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
