"""Canonical Sidecar database fixtures."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
import pytest_asyncio

from ibreeze.company import _sha256
from ibreeze.persistence.connection import open_writer
from ibreeze.persistence.migrator import MigrationRunner


class TransactionalTestConnection:
    """Test-only connection adapter for direct service-layer tests.

    Production commands enter through WriteQueue, which starts ``BEGIN
    IMMEDIATE`` before invoking a service.  These tests intentionally exercise
    services without booting the application, so the adapter supplies the
    same transaction precondition and opens the real SQLite transaction just
    before the first mutating statement.  PRAGMA setup remains outside a
    transaction, which is required by the fixture's foreign-key setup.
    """

    _MUTATING_SQL = {"INSERT", "UPDATE", "DELETE", "REPLACE", "WITH"}

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    @property
    def in_transaction(self) -> bool:
        # The scope is owned by this fixture even before SQLite has received a
        # mutating statement; this mirrors WriteQueue's precondition check.
        return True

    async def execute(self, sql: str, parameters: object = ()):
        statement = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if statement in self._MUTATING_SQL and not self._connection.in_transaction:
            await self._connection.execute("BEGIN IMMEDIATE")
        return await self._connection.execute(sql, parameters)

    async def commit(self) -> None:
        await self._connection.commit()

    async def rollback(self) -> None:
        await self._connection.rollback()

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


@pytest.fixture
def mock_db_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest_asyncio.fixture
async def local_db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    database = tmp_path / "profile.db"
    conn = await open_writer(database)
    runner = MigrationRunner(conn)
    await runner.apply_all()
    try:
        yield conn
    finally:
        if conn.in_transaction:
            await conn.rollback()
        await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        await conn.close()


@pytest_asyncio.fixture
async def db(local_db: aiosqlite.Connection) -> TransactionalTestConnection:
    return TransactionalTestConnection(local_db)


@pytest_asyncio.fixture
async def published_profile(db: aiosqlite.Connection) -> str:
    now = "2026-01-01T00:00:00.000000Z"
    release_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    # Create company and its required FK dependencies
    company_id = str(uuid.uuid4())
    revision_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    employee_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    dept_conv_id = str(uuid.uuid4())
    dept_rev_id = str(uuid.uuid4())

    # Disable FKs for test setup simplicity
    await db.execute("PRAGMA foreign_keys = OFF")

    await db.execute(
        """INSERT INTO company_revisions
           (id, company_id, revision_number, name, introduction, content_sha256,
            created_by_type, created_at)
           VALUES (?, ?, 1, 'TestCo', 'Test company', ?, 'system', ?)""",
        (revision_id, company_id, _sha256("test"), now),
    )
    # Create employee first (dept needs leader_employee_id)
    await db.execute(
        """INSERT INTO employees
           (id, company_id, department_id, display_name, normalized_display_name,
            base_profile_version_id, workflow_role, status, created_at, updated_at, version)
           VALUES (?, ?, ?, 'GM', 'gm', ?, 'general_manager', 'active', ?, ?, 1)""",
        (employee_id, company_id, dept_id, version_id, now, now),
    )
    await db.execute(
        """INSERT INTO department_revisions
           (id, department_id, company_id, revision_number, name, function_description,
            content_sha256, created_at)
           VALUES (?, ?, ?, 1, 'Root', 'Root dept', ?, ?)""",
        (dept_rev_id, dept_id, company_id, _sha256("root"), now),
    )
    await db.execute(
        """INSERT INTO conversations
           (id, company_id, conversation_type, status, created_at)
           VALUES (?, ?, 'department', 'active', ?)""",
        (dept_conv_id, company_id, now),
    )
    await db.execute(
        """INSERT INTO departments
           (id, company_id, department_type, normalized_name, current_revision_id,
            leader_employee_id, department_conversation_id, status, created_at, updated_at, version)
           VALUES (?, ?, 'general_manager_office', 'root', ?, ?, ?,
                   'active', ?, ?, 1)""",
        (dept_id, company_id, dept_rev_id, employee_id, dept_conv_id, now, now),
    )
    await db.execute(
        """INSERT INTO conversations
           (id, company_id, conversation_type, status, created_at)
           VALUES (?, ?, 'company', 'active', ?)""",
        (conv_id, company_id, now),
    )
    await db.execute(
        """INSERT INTO companies
           (id, normalized_name, current_revision_id, general_manager_office_id,
            general_manager_employee_id, company_conversation_id,
            status, created_at, updated_at, version)
           VALUES (?, 'testco', ?, ?, ?, ?, 'active', ?, ?, 1)""",
        (company_id, revision_id, dept_id, employee_id, conv_id, now, now),
    )

    # Re-enable FKs
    await db.execute("PRAGMA foreign_keys = ON")

    await db.execute(
        """INSERT INTO catalog_cache_releases
           (release_id, release_sequence, manifest_json, manifest_sha256,
            signature, signing_key_id, status, downloaded_at, activated_at)
           VALUES (?, 1, '{}', ?, 'signature', 'key-1', 'active', ?, ?)""",
        (release_id, _sha256("{}"), now, now),
    )
    await db.execute(
        """INSERT INTO employee_base_profiles
           (id, company_id, name, normalized_name, description, current_version_id,
            status, created_at, updated_at, version)
           VALUES (?, ?, 'Default', 'default', 'Default employee profile', ?,
                   'active', ?, ?, 1)""",
        (profile_id, company_id, version_id, now, now),
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
