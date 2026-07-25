"""Manifest builder and signing for catalog releases."""

import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.skill import Skill, SkillVersion
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.releases.manifest")


async def build_manifest(db: AsyncSession, sequence: int) -> dict:
    """Generate manifest from published skills with content hashes."""
    logger.info("build_manifest.start", extra={"sequence": sequence})
    result = await db.execute(select(Skill).where(Skill.status == "published"))
    skills = result.scalars().all()

    resources = []
    for skill in skills:
        version_result = await db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill.id)
            .order_by(SkillVersion.created_at.desc())
            .limit(1)
        )
        latest_version = version_result.scalar_one_or_none()
        content_sha256 = latest_version.content_sha256 if latest_version else ""

        resources.append(
            {
                "id": str(skill.id),
                "key": skill.key,
                "display_name": skill.display_name,
                "version": skill.version,
                "content_sha256": content_sha256,
            }
        )

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
