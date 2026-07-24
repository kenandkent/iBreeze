"""Company aggregate transaction tests."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.company import (
    _new_id,
    _normalize_name,
    archive_company,
    create_company,
    rename_company,
)
from ibreeze.schemas import CompanyCreate, CompanyUpdate


def _create(profile_id: str, *, name: str = "测试公司") -> CompanyCreate:
    return CompanyCreate(
        name=name,
        introduction="负责完整的软件交付流程",
        general_manager_name="总经理",
        base_profile_version_id=profile_id,
    )


def test_ids_are_canonical_uuid_v4() -> None:
    value = _new_id()
    parsed = uuid.UUID(value)
    assert parsed.version == 4
    assert str(parsed) == value


def test_name_normalization_is_nfkc_trimmed_and_casefolded() -> None:
    assert _normalize_name("  ＩBreeze   Dev  ") == "ibreeze dev"


@pytest.mark.asyncio
async def test_create_company_is_atomic(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    result = await create_company(db, _create(published_profile))
    assert result.status == "active"
    assert result.version == 1

    for table, expected in (
        ("companies", 1),
        ("company_revisions", 1),
        ("departments", 1),
        ("department_revisions", 1),
        ("department_responsibilities", 1),
        ("employees", 1),
        ("conversations", 2),
        ("domain_events", 1),
        ("outbox_events", 1),
    ):
        if table == "companies":
            sql, params = "SELECT COUNT(*) FROM companies WHERE id=?", (result.id,)
        elif table == "outbox_events":
            sql, params = "SELECT COUNT(*) FROM outbox_events", ()
        else:
            sql, params = f"SELECT COUNT(*) FROM {table} WHERE company_id=?", (result.id,)
        row = await (await db.execute(sql, params)).fetchone()
        assert row[0] == expected, table

    company = await (
        await db.execute("SELECT * FROM companies WHERE id=?", (result.id,))
    ).fetchone()
    office = await (
        await db.execute(
            "SELECT * FROM departments WHERE id=?",
            (company["general_manager_office_id"],),
        )
    ).fetchone()
    assert office["leader_employee_id"] == company["general_manager_employee_id"]
    assert (
        await (
            await db.execute(
                """SELECT COUNT(*) FROM conversations
                   WHERE company_id=? AND conversation_type='company'
                   AND department_id IS NULL""",
                (result.id,),
            )
        ).fetchone()
    )[0] == 1


@pytest.mark.asyncio
async def test_create_rejects_duplicate_and_unpublished_profile(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    await create_company(db, _create(published_profile, name="Same"))
    with pytest.raises(ValueError, match="NAME_EXISTS"):
        await create_company(db, _create(published_profile, name="  SAME "))
    with pytest.raises(ValueError, match="BASE_PROFILE_NOT_PUBLISHED"):
        await create_company(db, _create(str(uuid.uuid4()), name="Other"))


@pytest.mark.asyncio
async def test_update_creates_revision_and_enforces_version(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    created = await create_company(db, _create(published_profile))
    updated = await rename_company(
        db,
        created.id,
        CompanyUpdate(
            name="新公司",
            introduction="新的流转说明",
            expected_version=1,
        ),
        expected_version=1,
    )
    assert updated.normalized_name == "新公司"
    assert updated.version == 2
    revision = await (
        await db.execute(
            "SELECT name,introduction FROM company_revisions WHERE id=?",
            (updated.current_revision_id,),
        )
    ).fetchone()
    assert tuple(revision) == ("新公司", "新的流转说明")
    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        await rename_company(
            db,
            created.id,
            CompanyUpdate(name="过期写入", expected_version=1),
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_archive_cascades_idle_aggregate(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    created = await create_company(db, _create(published_profile))
    archived = await archive_company(db, created.id, expected_version=1)
    assert archived.status == "archived"
    departments = await (
        await db.execute(
            "SELECT DISTINCT status FROM departments WHERE company_id=?",
            (created.id,),
        )
    ).fetchall()
    employees = await (
        await db.execute(
            "SELECT DISTINCT status FROM employees WHERE company_id=?",
            (created.id,),
        )
    ).fetchall()
    assert [row[0] for row in departments] == ["archived"]
    assert [row[0] for row in employees] == ["inactive"]
