"""Manifest builder and signing for catalog releases."""

import base64
import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.observability.logging_config import get_logger
from ibreeze_backend.releases.bundle import freeze_resources
from ibreeze_backend.releases.canonical_json import canonical_bytes

logger = get_logger("ibreeze.releases.manifest")


async def build_manifest(
    db: AsyncSession,
    release_id: uuid.UUID,
    sequence: int,
    minimum_client_version: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    logger.info("build_manifest.start", extra={"sequence": sequence, "release_id": str(release_id)})
    if created_at is None:
        created_at = datetime.now(UTC)

    resources = await freeze_resources(db, release_id, sequence)

    manifest: dict[str, Any] = {
        "release_id": str(release_id),
        "release_sequence": sequence,
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "minimum_client_version": minimum_client_version,
        "signature_algorithm": "Ed25519",
        "resources": resources,
    }
    logger.info("build_manifest.completed", extra={"sequence": sequence, "resource_count": len(resources)})
    return manifest


def compute_manifest_signature(manifest_bytes: bytes, private_key: Ed25519PrivateKey) -> str:
    """Sign manifest bytes with Ed25519 and return padded standard Base64.

    The desktop updater decodes release-manifest signatures with the standard
    RFC 4648 alphabet.  Keeping the padding is part of that wire contract and
    avoids ambiguous decoding of a 64-byte Ed25519 signature.
    """
    signature = private_key.sign(manifest_bytes)
    return base64.b64encode(signature).decode("ascii")


def manifest_to_bytes(manifest: dict[str, Any]) -> bytes:
    """Canonicalize manifest to deterministic bytes using RFC 8785."""
    return canonical_bytes(manifest)
