"""Release management tests — manifest generation, signing, emergency disable.

Covers design spec sections:
- G.9 Catalog Release (manifest, signing, emergency disable)
"""
import uuid
from unittest.mock import MagicMock

import pytest


def _mock_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


class TestManifestGeneration:
    """Manifest generation from active skills."""

    @pytest.mark.asyncio
    async def test_generate_manifest(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        skill = MagicMock()
        skill.id = uuid.uuid4()
        skill.name = "test-skill"
        skill.version = "1.0.0"
        skill.category = "dev"
        skill.compatibility = None
        skill.checksum = "abc123"

        mock_db_session.execute.return_value = _mock_scalars([skill])

        manifest = await build_manifest(mock_db_session, sequence=1)
        assert manifest["release_sequence"] == 1
        assert len(manifest["resources"]) == 1
        assert manifest["resources"][0]["name"] == "test-skill"

    @pytest.mark.asyncio
    async def test_sign_manifest(self):
        from ibreeze_backend.releases.manifest import (
            compute_manifest_signature,
            manifest_to_bytes,
        )
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        manifest = {"release_sequence": 1, "resources": []}
        manifest_bytes = manifest_to_bytes(manifest)

        sig = compute_manifest_signature(manifest_bytes, private_key)
        assert isinstance(sig, str)
        assert len(sig) > 0


class TestEmergencyDisable:
    """Emergency disable with monotonic sequence."""

    @pytest.mark.asyncio
    async def test_emergency_disable(self, mock_db_session):
        from ibreeze_backend.releases.emergency import create_emergency_disable

        mock_db_session.execute.return_value = _mock_scalars([])

        disable = await create_emergency_disable(mock_db_session, ["skill-1", "skill-2"])
        assert disable.sequence == 1
        assert disable.disabled_skill_ids == ["skill-1", "skill-2"]
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_emergency_disable_monotonic_sequence(self, mock_db_session):
        from ibreeze_backend.releases.emergency import create_emergency_disable

        existing = MagicMock()
        existing.sequence = 5

        mock_db_session.execute.return_value = _mock_scalars([existing])

        disable = await create_emergency_disable(mock_db_session, ["skill-1"])
        assert disable.sequence == 6


class TestReleaseIdempotency:
    """Release idempotency checks."""

    @pytest.mark.asyncio
    async def test_release_idempotency(self, mock_db_session):
        from ibreeze_backend.releases.emergency import get_latest_emergency_disable

        existing = MagicMock()
        existing.sequence = 10

        mock_db_session.execute.return_value = _mock_result(existing)

        result = await get_latest_emergency_disable(mock_db_session)
        assert result is not None
        assert result.sequence == 10

    @pytest.mark.asyncio
    async def test_release_idempotency_none(self, mock_db_session):
        from ibreeze_backend.releases.emergency import get_latest_emergency_disable

        mock_db_session.execute.return_value = _mock_result(None)

        result = await get_latest_emergency_disable(mock_db_session)
        assert result is None
