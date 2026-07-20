"""SC-40-2 / SC-40-4 缺陷修复验证。"""

from __future__ import annotations

import aiosqlite
import pytest

from acos.rpc.errors import AcosError, BACKEND_UNAVAILABLE, RT_SESSION_READONLY
from acos.rpc.methods_session import SessionMethods
from tests.runtime.conftest import seed_company_employee

pytestmark = pytest.mark.asyncio


async def _seed_template(db_path: str, template_id: str, status: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO employee_templates
               (template_id, company_id, capability_id, capability_version,
                default_role, status, version, created_at, updated_at)
               VALUES (?, 'co1', 'cap', 1, '员工', ?, 1, datetime('now'), datetime('now'))""",
            (template_id, status),
        )
        await db.commit()


async def test_sc_40_2_suspended_employee_readonly(migrated_db) -> None:
    db_path, root = migrated_db
    await seed_company_employee(db_path)  # 默认模板 tpl（未建模板行，tpl_status=None）
    m = SessionMethods(db_path, root)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE employees SET status='suspended' WHERE employee_id='emp1'")
        await db.commit()
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "message": "x",
            "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_READONLY


async def test_sc_40_2_archived_template_readonly(migrated_db) -> None:
    db_path, root = migrated_db
    await seed_company_employee(db_path)
    await _seed_template(db_path, "tpl", "archived")
    m = SessionMethods(db_path, root)
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "message": "x",
            "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_READONLY


async def test_sc_40_2_active_template_ok(migrated_db) -> None:
    db_path, root = migrated_db
    await seed_company_employee(db_path)
    await _seed_template(db_path, "tpl", "active")
    m = SessionMethods(db_path, root)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    assert r["thread_id"]


async def test_sc_40_4_require_backend_creates_intervention(migrated_db) -> None:
    db_path, root = migrated_db
    await seed_company_employee(db_path)  # 不 seed backend
    m = SessionMethods(db_path, root, require_backend=True)
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "message": "x",
            "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == BACKEND_UNAVAILABLE
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM human_interventions WHERE subtype='backend_recovery'"
        )
        row = await cur.fetchone()
        assert row is not None
        assert row["target_ref"] == "backend_lease:co1"
        assert row["company_id"] == "co1"
        assert row["status"] == "open"


async def test_sc_40_4_default_no_backend_silent(migrated_db) -> None:
    db_path, root = migrated_db
    await seed_company_employee(db_path)  # 不 seed backend
    m = SessionMethods(db_path, root)  # require_backend 默认 False
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    assert r["thread_id"]
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM human_interventions WHERE subtype='backend_recovery'"
        )
        assert (await cur.fetchone())["c"] == 0
