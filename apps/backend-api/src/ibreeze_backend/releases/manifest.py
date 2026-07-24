"""Manifest builder and signing for catalog releases."""

import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.skill import Skill


async def build_manifest(db: AsyncSession, sequence: int) -> dict:
    """Generate manifest from active skills with content hashes."""
    result = await db.execute(select(Skill).where(Skill.status.in_(["published", "active"])))
    skills = result.scalars().all()

    resources = []
    for skill in skills:
        resources.append(
            {
                "id": str(skill.id),
                "name": skill.name,
                "version": skill.version,
                "category": skill.category,
                "compatibility": skill.compatibility,
                "content_sha256": skill.checksum or "",
            }
        )

    manifest = {
        "release_sequence": sequence,
        "resources": resources,
    }
    return manifest


def compute_manifest_signature(manifest_bytes: bytes, private_key: Ed25519PrivateKey) -> str:
    """Sign manifest bytes with Ed25519 and return hex signature."""
    signature = private_key.sign(manifest_bytes)
    return signature.hex()


def manifest_to_bytes(manifest: dict) -> bytes:
    """Canonicalize manifest to deterministic bytes."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
