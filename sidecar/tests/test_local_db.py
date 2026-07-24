"""Profile identity initialization tests."""

from __future__ import annotations

import uuid

import pytest

from ibreeze.local_db import LocalDB


@pytest.mark.asyncio
async def test_profile_identity_is_created_online_and_verified_offline(local_db: LocalDB) -> None:
    profile_id = uuid.uuid4().hex
    user_id = str(uuid.uuid4())
    device_id = str(uuid.uuid4())
    values = {
        "profile_id": profile_id,
        "backend_origin": "https://example.com:443",
        "app_user_id": user_id,
        "masked_identifier": "u***@example.com",
        "device_id": device_id,
    }
    await local_db.initialize_profile(**values, allow_create=True)
    await local_db.initialize_profile(**values, allow_create=False)
    row = await local_db.fetch_one("SELECT * FROM local_profile")
    assert row is not None
    assert row["id"] == profile_id
    assert row["backend_origin"] == values["backend_origin"]
    assert row["app_user_id"] == user_id
    assert row["device_id"] == device_id


@pytest.mark.asyncio
async def test_offline_open_rejects_missing_or_mismatched_profile(local_db: LocalDB) -> None:
    values = {
        "profile_id": uuid.uuid4().hex,
        "backend_origin": "https://example.com:443",
        "app_user_id": str(uuid.uuid4()),
        "masked_identifier": "u***@example.com",
        "device_id": str(uuid.uuid4()),
    }
    with pytest.raises(ValueError, match="PROFILE_IDENTITY_MISSING"):
        await local_db.initialize_profile(**values, allow_create=False)
    await local_db.initialize_profile(**values, allow_create=True)
    with pytest.raises(ValueError, match="PROFILE_IDENTITY_MISMATCH"):
        await local_db.initialize_profile(
            **{**values, "backend_origin": "https://other.example:443"},
            allow_create=False,
        )
