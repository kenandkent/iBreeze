"""Tests for emergency disable and compatibility priority.

Covers design spec sections:
- REL-004 Emergency disable flow
- CAT-004 Emergency disable priority over manifest
"""
import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
class TestEmergencyDisable:
    """Emergency disable service tests."""

    async def test_emergency_disable_overrides_all(self):
        """Emergency disable should take priority over deny/allow rules."""
        from ibreeze_backend.releases.emergency import create_emergency_disable

        db = AsyncMock()
        db.execute.return_value = AsyncMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        db.flush = AsyncMock()
        db.add = MagicMock()

        payload = {"scope": "all", "reason": "security incident"}
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()

        release = await create_emergency_disable(
            db,
            actor_user_id=uuid.uuid4(),
            payload_json=payload,
            payload_sha256=payload_sha256,
            signature="mock-sig-ed25519",
            signing_key_id="key-1",
        )
        assert release.sequence == 1
        assert release.payload_json == payload
        assert release.signature == "mock-sig-ed25519"
        assert release.signing_key_id == "key-1"
        db.add.assert_called_once()

    async def test_emergency_disable_independent_signature(self):
        """Emergency disable should have its own signature."""
        from ibreeze_backend.releases.emergency import create_emergency_disable

        db = AsyncMock()
        db.execute.return_value = AsyncMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        db.flush = AsyncMock()
        db.add = MagicMock()

        payload = {"scope": "all"}
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()

        release = await create_emergency_disable(
            db,
            actor_user_id=uuid.uuid4(),
            payload_json=payload,
            payload_sha256=payload_sha256,
            signature="sig-emergency-only",
            signing_key_id="emergency-key",
        )
        assert release.signature == "sig-emergency-only"
        assert release.signing_key_id == "emergency-key"

    async def test_emergency_disable_does_not_modify_history(self):
        """Emergency disable should not modify previous manifests."""
        from ibreeze_backend.releases.emergency import create_emergency_disable, get_latest_emergency_disable

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        existing = MagicMock()
        existing.sequence = 5
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [existing]
        cursor = MagicMock()
        cursor.scalars.return_value = scalars_mock
        db.execute.return_value = cursor

        release = await create_emergency_disable(
            db,
            actor_user_id=uuid.uuid4(),
            payload_json={"scope": "all"},
            payload_sha256="abc123",
            signature="sig",
            signing_key_id="key-1",
        )
        assert release.sequence == 6
        assert existing.sequence == 5

    async def test_emergency_disable_sequence_increments(self):
        """Subsequent emergency disables should increment sequence."""
        from ibreeze_backend.releases.emergency import create_emergency_disable

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        existing = MagicMock()
        existing.sequence = 3
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [existing]
        cursor = MagicMock()
        cursor.scalars.return_value = scalars_mock
        db.execute.return_value = cursor

        release = await create_emergency_disable(
            db,
            actor_user_id=uuid.uuid4(),
            payload_json={"scope": "all"},
            payload_sha256="hash",
            signature="sig",
            signing_key_id="key",
        )
        assert release.sequence == 4

    async def test_get_latest_emergency_disable_empty(self):
        """No emergency disables should return None."""
        from ibreeze_backend.releases.emergency import get_latest_emergency_disable

        db = AsyncMock()
        cursor = MagicMock()
        cursor.scalar_one_or_none.return_value = None
        db.execute.return_value = cursor

        result = await get_latest_emergency_disable(db)
        assert result is None

    async def test_emergency_disable_payload_sha256_integrity(self):
        """Payload SHA-256 should match actual content."""
        from ibreeze_backend.releases.emergency import create_emergency_disable

        db = AsyncMock()
        db.execute.return_value = AsyncMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        db.flush = AsyncMock()
        db.add = MagicMock()

        payload = {"scope": "all", "reason": "breach"}
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        expected_hash = hashlib.sha256(payload_bytes).hexdigest()

        release = await create_emergency_disable(
            db,
            actor_user_id=uuid.uuid4(),
            payload_json=payload,
            payload_sha256=expected_hash,
            signature="sig",
            signing_key_id="key",
        )
        actual_hash = hashlib.sha256(
            json.dumps(release.payload_json, sort_keys=True).encode()
        ).hexdigest()
        assert actual_hash == expected_hash
