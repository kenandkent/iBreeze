"""Canonical Sidecar database fixtures."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from ibreeze.company import _sha256
from ibreeze.local_db import LocalDB


@pytest_asyncio.fixture
async def local_db(tmp_path: Path) -> AsyncIterator[LocalDB]:
    database = LocalDB(tmp_path / "profile.db", read_pool_size=1)
    await database.initialize()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def db(local_db: LocalDB) -> aiosqlite.Connection:
    return local_db.write_connection


@pytest_asyncio.fixture
async def published_profile(db: aiosqlite.Connection) -> str:
    now = "2026-01-01T00:00:00.000000Z"
    release_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO catalog_cache_releases
           (release_id, release_sequence, manifest_json, manifest_sha256,
            signature, signing_key_id, status, downloaded_at, activated_at)
           VALUES (?, 1, '{}', ?, 'signature', 'key-1', 'active', ?, ?)""",
        (release_id, _sha256("{}"), now, now),
    )
    await db.execute(
        """INSERT INTO employee_base_profiles
           (id, name, normalized_name, description, current_version_id,
            status, created_at, updated_at, version)
           VALUES (?, 'Default', 'default', 'Default employee profile', ?,
                   'active', ?, ?, 1)""",
        (profile_id, version_id, now, now),
    )
    await db.execute(
        """INSERT INTO employee_base_profile_versions
           (id, profile_id, version_number, name, description, profile_type,
            runtime_binding_json, system_prompt, capability_tags_json,
            tool_policy_json, timeout_seconds, max_retries, workspace_policy,
            catalog_release_id, content_sha256, status, created_at, published_at)
           VALUES (?, ?, 1, 'Default v1', 'Default employee profile',
                   'agent_cli', '{"adapter_type":"codex_cli"}', 'Act carefully.',
                   '[]', '{}', 300, 2, 'workspace_rw_external_ro', ?, ?,
                   'published', ?, ?)""",
        (
            version_id,
            profile_id,
            release_id,
            _sha256("default-profile-v1"),
            now,
            now,
        ),
    )
    await db.commit()
    return version_id


@pytest.fixture
def uuid_value() -> str:
    return str(uuid.uuid4())
