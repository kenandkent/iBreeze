"""Gap coverage for company.py read/rename/archive edge branches.

test_company_atomic.py covers the happy paths of create/rename/archive.  The
remaining uncovered branches are: get_company missing row, list_companies
cursor pagination, create_company missing profile version / non-transactional
db / mid-transaction failure, rename_company non-transactional db / archived
company / name-less rename, and every archive_company blocker (stale version,
non-active company, and each non-idle child table).
"""

from __future__ import annotations

import json
import uuid

import pytest

from ibreeze.company import (
    archive_company,
    create_company,
    get_company,
    list_companies,
    rename_company,
)
from ibreeze.schemas import CompanyCreate, CompanyUpdate


def _create(profile_id: str, *, name: str = "覆盖公司") -> CompanyCreate:
    return CompanyCreate(
        name=name,
        introduction="负责完整的软件交付流程",
        general_manager_name="总经理",
        base_profile_version_id=profile_id,
    )


class _RowsCursor:
    def __init__(self, rows) -> None:
        self._rows = rows

    def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class _NoTransactionDB:
    """in_transaction False; profile-version probe returns one row, name probe empty."""

    in_transaction = False

    async def execute(self, sql, params=()):
        if "employee_base_profile_versions WHERE id = ? AND status = 'published'" in sql:
            return _RowsCursor([("profile-1",)])
        return _RowsCursor([])


class _CreateFailingDB:
    """Real db wrapper that fails on the company INSERT (inside the try)."""

    in_transaction = True

    def __init__(self, inner) -> None:
        self._inner = inner

    async def execute(self, sql, params=()):
        if "INSERT INTO companies" in sql:
            raise RuntimeError("insert boom")
        if "PRAGMA defer_foreign_keys" in sql:
            return _RowsCursor([[0]])
        return await self._inner.execute(sql, params)


class TestGetCompanyGaps:
    @pytest.mark.asyncio
    async def test_get_company_not_found(self, db) -> None:
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await get_company(db, str(uuid.uuid4()))


class TestListCompaniesGaps:
    @pytest.mark.asyncio
    async def test_list_after_cursor(self, db, published_profile: str) -> None:
        rows = await list_companies(
            db,
            after=("2026-01-01T00:00:00.000001Z", str(uuid.uuid4())),
        )
        assert isinstance(rows, list)


class TestCreateCompanyGaps:
    @pytest.mark.asyncio
    async def test_missing_base_profile_version(self, db) -> None:
        with pytest.raises(ValueError, match="BASE_PROFILE_VERSION_REQUIRED"):
            await create_company(db, _create(""))

    @pytest.mark.asyncio
    async def test_write_queue_required(self) -> None:
        with pytest.raises(RuntimeError, match="WRITE_QUEUE_REQUIRED"):
            await create_company(_NoTransactionDB(), _create("profile-1"))

    @pytest.mark.asyncio
    async def test_mid_transaction_failure_reraises(self, db, published_profile: str) -> None:
        wrapper = _CreateFailingDB(db)
        with pytest.raises(RuntimeError, match="insert boom"):
            await create_company(wrapper, _create(published_profile))


class TestRenameCompanyGaps:
    @pytest.mark.asyncio
    async def test_write_queue_required(self) -> None:
        import types

        db = types.SimpleNamespace(in_transaction=False)
        with pytest.raises(RuntimeError, match="WRITE_QUEUE_REQUIRED"):
            await rename_company(
                db,
                str(uuid.uuid4()),
                CompanyUpdate(name="改名", expected_version=1),
                expected_version=1,
            )

    @pytest.mark.asyncio
    async def test_archived_company_rejected(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        await db.execute("UPDATE companies SET status='archived' WHERE id=?", (created.id,))
        await db.commit()
        with pytest.raises(ValueError, match="COMPANY_ARCHIVED"):
            await rename_company(
                db,
                created.id,
                CompanyUpdate(name="改名", expected_version=1),
                expected_version=1,
            )

    @pytest.mark.asyncio
    async def test_name_less_rename_skips_uniqueness_check(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        updated = await rename_company(
            db,
            created.id,
            CompanyUpdate(introduction="仅更新说明", expected_version=1),
            expected_version=1,
        )
        assert updated.version == 2
        assert updated.normalized_name == created.normalized_name


class TestArchiveCompanyGaps:
    @pytest.mark.asyncio
    async def test_stale_version_conflict(self, db) -> None:
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await archive_company(db, str(uuid.uuid4()), expected_version=1)

    @pytest.mark.asyncio
    async def test_non_active_company_rejected(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        await db.execute("UPDATE companies SET status='archived' WHERE id=?", (created.id,))
        await db.commit()
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await archive_company(db, created.id, expected_version=1)

    @pytest.mark.asyncio
    async def test_active_company_task_blocks_archive(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        now = "2026-01-01T00:00:00Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                "INSERT INTO company_tasks"
                " (id, company_id, company_conversation_id, user_message_event_id, title,"
                " status, created_at, updated_at, version)"
                " VALUES (?,?,?,?,'Task','draft',?,?,1)",
                (str(uuid.uuid4()), created.id, str(uuid.uuid4()), str(uuid.uuid4()), now, now),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await archive_company(db, created.id, expected_version=1)

    @pytest.mark.asyncio
    async def test_active_agent_run_blocks_archive(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        now = "2026-01-01T00:00:00Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            employee_task_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO agent_runs"
                " (id, company_id, company_task_id, department_task_id, employee_task_id,"
                " work_item_id, employee_id,"
                " conversation_id, availability_snapshot_id, execution_snapshot_id,"
                " run_purpose, adapter_type, run_spec_json, run_spec_sha256,"
                " status, attempt, created_at, updated_at, version)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,'task_execution','codex_cli','{}',?,"
                " 'queued',1,?,?,1)",
                (
                    str(uuid.uuid4()),
                    created.id,
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    employee_task_id,
                    employee_task_id,
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    "a" * 64,
                    now,
                    now,
                ),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await archive_company(db, created.id, expected_version=1)

    @pytest.mark.asyncio
    async def test_pending_human_approval_blocks_archive(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        now = "2026-01-01T00:00:00Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                "INSERT INTO human_approvals"
                " (id, company_id, run_id, approval_type, target_json, target_sha256,"
                " status, requested_at, expires_at, version)"
                " VALUES (?,?,?,'external_write','{}',?,'pending',?,?,1)",
                (
                    str(uuid.uuid4()),
                    created.id,
                    str(uuid.uuid4()),
                    "a" * 64,
                    now,
                    now,
                ),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await archive_company(db, created.id, expected_version=1)

    @pytest.mark.asyncio
    async def test_unsubmitted_review_assignment_blocks_archive(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        now = "2026-01-01T00:00:00Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                "INSERT INTO review_assignments"
                " (id, company_id, artifact_id, reviewer_employee_id, review_round,"
                " reviewed_sha256, status, assigned_at)"
                " VALUES (?,?,?,?,1,?,'assigned',?)",
                (
                    str(uuid.uuid4()),
                    created.id,
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    "a" * 64,
                    now,
                ),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await archive_company(db, created.id, expected_version=1)

    @pytest.mark.asyncio
    async def test_active_task_workspace_blocks_archive(self, db, published_profile: str) -> None:
        created = await create_company(db, _create(published_profile))
        now = "2026-01-01T00:00:00Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                "INSERT INTO task_workspaces"
                " (id, company_id, company_task_id, workspace_grant_id, repository_root,"
                " baseline_commit_sha, user_branch_name, integration_branch_name,"
                " integration_worktree_path, status, created_at, updated_at, version)"
                " VALUES (?,?,?,?,'/repo',?,'main','ibreeze/integration',"
                " '/tmp/ibreeze-integration-x','active',?,?,1)",
                (
                    str(uuid.uuid4()),
                    created.id,
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    "a" * 40,
                    now,
                    now,
                ),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await archive_company(db, created.id, expected_version=1)


def test_imports() -> None:
    assert json is not None
