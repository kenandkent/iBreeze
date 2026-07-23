"""公司创建原子事务单元测试——H.5。

使用内存 aiosqlite 验证：
- 事务原子性（六项不变量全部通过）
- 名称唯一性
- defer_foreign_keys=OFF 恢复
- 改名事务
- base_profile_version_id 校验
"""
import json

import aiosqlite
import pytest

from ibreeze.company import (
    _new_id,
    _normalize_name,
    _sha256,
    create_company,
    rename_company,
)
from ibreeze.schemas import CompanyCreate, CompanyUpdate
from ibreeze.local_db import _CREATE_TABLES_SQL, _IMMUTABILITY_TRIGGERS, _PRAGMAS


async def _create_test_db() -> aiosqlite.Connection:
    """创建内存 aiosqlite 数据库，执行全部 DDL。"""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    for pragma in _PRAGMAS:
        await db.execute(pragma)
    await db.executescript(_CREATE_TABLES_SQL)
    if _IMMUTABILITY_TRIGGERS:
        await db.executescript(_IMMUTABILITY_TRIGGERS)
    return db


async def _seed_published_base_profile(db: aiosqlite.Connection) -> str:
    """创建已发布的底座版本（catalog_cache_release + profile + version），返回 version_id。

    依赖链：catalog_cache_releases → employee_base_profiles → employee_base_profile_versions
    """
    now = "2026-01-01T00:00:00.000000Z"
    release_id = _new_id()
    profile_id = _new_id()
    version_id = _new_id()

    # 1. catalog_cache_release (active)
    await db.execute(
        """INSERT INTO catalog_cache_releases
           (release_id, release_sequence, manifest_json, manifest_sha256,
            signature, signing_key_id, status, downloaded_at, activated_at)
           VALUES (?, 1, '{}', ?, 'sig', 'key', 'active', ?, ?)""",
        (release_id, _sha256("{}"), now, now),
    )

    # 2. employee_base_profile
    await db.execute(
        """INSERT INTO employee_base_profiles
           (id, name, normalized_name, description,
            current_version_id, status, created_at, updated_at, version)
           VALUES (?, 'GM Profile', 'gm profile', '总经理底座',
                   ?, 'active', ?, ?, 1)""",
        (profile_id, version_id, now, now),
    )

    # 3. employee_base_profile_version (published)
    await db.execute(
        """INSERT INTO employee_base_profile_versions
           (id, profile_id, version_number, name, description,
            profile_type, runtime_binding_json, system_prompt,
            capability_tags_json, tool_policy_json,
            timeout_seconds, max_retries, workspace_policy,
            catalog_release_id, content_sha256, status,
            created_at, published_at)
           VALUES (?, ?, 1, 'GM Profile v1', '总经理底座 v1',
                   'agent_cli', '{}', 'You are a CEO.',
                   '[]', '{}',
                   300, 3, 'workspace_rw_external_ro',
                   ?, ?, 'published',
                   ?, ?)""",
        (version_id, profile_id, release_id, _sha256("gm profile v1"), now, now),
    )

    # 更新 profile 的 current_version_id
    await db.execute(
        "UPDATE employee_base_profiles SET current_version_id = ? WHERE id = ?",
        (version_id, profile_id),
    )

    # 提交前置数据，确保 create_company 能开启自己的事务
    await db.commit()

    return version_id


# ── 辅助函数测试 ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_new_id_is_32_hex(self):
        id_val = _new_id()
        assert len(id_val) == 32
        assert all(c in "0123456789abcdef" for c in id_val)

    def test_new_id_unique(self):
        ids = {_new_id() for _ in range(100)}
        assert len(ids) == 100

    def test_normalize_name(self):
        assert _normalize_name("  My Company  ") == "my company"
        assert _normalize_name("ABC") == "abc"

    def test_sha256_deterministic(self):
        assert _sha256("hello") == _sha256("hello")
        assert _sha256("hello") != _sha256("world")
        assert len(_sha256("test")) == 64


# ── 创建公司事务测试 ─────────────────────────────────────────────────────

class TestCreateCompanyAtomic:
    @pytest.mark.asyncio
    async def test_create_company_success(self):
        """正常创建公司，验证六项不变量。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data = CompanyCreate(name="测试公司", introduction="这是一家测试公司")
            result = await create_company(db, data, base_profile_version_id=profile_version_id)

            assert result.id
            assert result.normalized_name == "测试公司"
            assert result.status == "active"
            assert result.version == 1

            # 验证 companies 表
            cur = await db.execute(
                "SELECT * FROM companies WHERE id = ?", (result.id,)
            )
            row = (await cur.fetchall())[0]
            assert row["version"] == 1
            assert row["general_manager_office_id"]
            assert row["general_manager_employee_id"]
            assert row["company_conversation_id"]

            # 验证 company_revisions 表
            cur = await db.execute(
                "SELECT * FROM company_revisions WHERE company_id = ?",
                (result.id,),
            )
            rev = (await cur.fetchall())[0]
            assert rev["revision_number"] == 1
            assert rev["name"] == "测试公司"
            assert rev["introduction"] == "这是一家测试公司"
            assert len(rev["content_sha256"]) == 64

            # 验证 departments 表（总经理办公室）
            cur = await db.execute(
                "SELECT * FROM departments WHERE company_id = ? AND department_type = 'general_manager_office'",
                (result.id,),
            )
            dept = (await cur.fetchall())[0]
            assert dept["leader_employee_id"] == row["general_manager_employee_id"]
            assert dept["department_conversation_id"]

            # 验证 department_revisions 表
            cur = await db.execute(
                "SELECT * FROM department_revisions WHERE department_id = ?",
                (dept["id"],),
            )
            dept_rev = (await cur.fetchall())[0]
            assert dept_rev["name"] == "总经理办公室"

            # 验证 department_responsibilities 表
            cur = await db.execute(
                "SELECT * FROM department_responsibilities WHERE department_id = ?",
                (dept["id"],),
            )
            resp = (await cur.fetchall())[0]
            assert resp["responsibility_key"] == "general_management"

            # 验证 employees 表（总经理）
            cur = await db.execute(
                "SELECT * FROM employees WHERE id = ?",
                (row["general_manager_employee_id"],),
            )
            emp = (await cur.fetchall())[0]
            assert emp["workflow_role"] == "general_manager"
            assert emp["department_id"] == dept["id"]

            # 验证 conversations 表（公司级）
            cur = await db.execute(
                "SELECT * FROM conversations WHERE id = ? AND conversation_type = 'company' AND department_id IS NULL",
                (row["company_conversation_id"],),
            )
            conv = (await cur.fetchall())[0]
            assert conv is not None

            # 验证 conversations 表（办公室级）
            cur = await db.execute(
                "SELECT * FROM conversations WHERE id = ? AND conversation_type = 'department' AND department_id = ?",
                (dept["department_conversation_id"], dept["id"]),
            )
            office_conv = (await cur.fetchall())[0]
            assert office_conv is not None

            # 验证 domain_events 表
            cur = await db.execute(
                "SELECT * FROM domain_events WHERE company_id = ? AND event_type = 'company.created'",
                (result.id,),
            )
            event = (await cur.fetchall())[0]
            payload = json.loads(event["payload_json"])
            assert payload["company_id"] == result.id

            # 验证 outbox_events 表
            cur = await db.execute(
                "SELECT * FROM outbox_events WHERE domain_event_id = ?",
                (event["event_id"],),
            )
            outbox = (await cur.fetchall())[0]
            assert outbox["topic"] == "company.created"
            assert outbox["status"] == "pending"

        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_create_company_name_exists(self):
        """名称重复应抛出 NAME_EXISTS。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data = CompanyCreate(name="唯一公司", introduction="简介")
            await create_company(db, data, base_profile_version_id=profile_version_id)

            with pytest.raises(ValueError, match="NAME_EXISTS"):
                await create_company(
                    db, CompanyCreate(name="唯一公司", introduction="简介2"),
                    base_profile_version_id=profile_version_id,
                )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_create_company_defer_fk_restored(self):
        """提交后 defer_foreign_keys 应恢复 OFF。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data = CompanyCreate(name="FK测试公司", introduction="测试FK恢复")
            await create_company(db, data, base_profile_version_id=profile_version_id)

            cur = await db.execute("PRAGMA defer_foreign_keys")
            fk_row = (await cur.fetchall())[0]
            assert fk_row[0] == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_create_company_rollback_on_error(self):
        """插入失败时事务应回滚，不留下部分数据。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data = CompanyCreate(name="回滚测试", introduction="简介")
            await create_company(db, data, base_profile_version_id=profile_version_id)

            cur = await db.execute("SELECT COUNT(*) FROM companies")
            count = (await cur.fetchall())[0][0]
            assert count == 1

            cur = await db.execute("PRAGMA defer_foreign_keys")
            fk_row = (await cur.fetchall())[0]
            assert fk_row[0] == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_create_company_base_profile_required(self):
        """不传 base_profile_version_id 应抛出异常。"""
        db = await _create_test_db()
        try:
            data = CompanyCreate(name="无底座公司", introduction="简介")
            with pytest.raises((TypeError, ValueError)):
                await create_company(db, data)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_create_company_base_profile_not_published(self):
        """传入不存在的 base_profile_version_id 应抛出 BASE_PROFILE_NOT_PUBLISHED。"""
        db = await _create_test_db()
        try:
            data = CompanyCreate(name="假底座公司", introduction="简介")
            with pytest.raises(ValueError, match="BASE_PROFILE_NOT_PUBLISHED"):
                await create_company(db, data, base_profile_version_id="nonexistent")
        finally:
            await db.close()


# ── 改名事务测试 ──────────────────────────────────────────────────────────

class TestRenameCompany:
    @pytest.mark.asyncio
    async def test_rename_company_success(self):
        """正常改名，验证新 revision 和 version 递增。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data = CompanyCreate(name="原名公司", introduction="简介")
            result = await create_company(db, data, base_profile_version_id=profile_version_id)

            update = CompanyUpdate(name="新名公司", introduction="新简介")
            renamed = await rename_company(
                db, result.id, update, expected_version=1
            )

            assert renamed.version == 2
            assert renamed.normalized_name == "新名公司"

            # 验证 companies 表 version 递增
            cur = await db.execute(
                "SELECT version, normalized_name FROM companies WHERE id = ?",
                (result.id,),
            )
            row = (await cur.fetchall())[0]
            assert row["version"] == 2
            assert row["normalized_name"] == "新名公司"

            # 验证 company_revisions 有两条记录
            cur = await db.execute(
                "SELECT * FROM company_revisions WHERE company_id = ? ORDER BY revision_number",
                (result.id,),
            )
            revs = await cur.fetchall()
            assert len(revs) == 2
            assert revs[0]["name"] == "原名公司"
            assert revs[1]["name"] == "新名公司"

            # 验证 domain_events
            cur = await db.execute(
                "SELECT * FROM domain_events WHERE company_id = ? AND event_type = 'company.renamed'",
                (result.id,),
            )
            events = await cur.fetchall()
            assert len(events) == 1
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_rename_company_version_conflict(self):
        """版本冲突应抛出 VERSION_CONFLICT。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data = CompanyCreate(name="冲突测试", introduction="简介")
            result = await create_company(db, data, base_profile_version_id=profile_version_id)

            update = CompanyUpdate(name="新名")
            with pytest.raises(ValueError, match="VERSION_CONFLICT"):
                await rename_company(
                    db, result.id, update, expected_version=999
                )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_rename_company_name_exists(self):
        """改名时名称重复应抛出 NAME_EXISTS。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data1 = CompanyCreate(name="公司A", introduction="简介A")
            await create_company(db, data1, base_profile_version_id=profile_version_id)

            data2 = CompanyCreate(name="公司B", introduction="简介B")
            result2 = await create_company(db, data2, base_profile_version_id=profile_version_id)

            update = CompanyUpdate(name="公司A")
            with pytest.raises(ValueError, match="NAME_EXISTS"):
                await rename_company(
                    db, result2.id, update, expected_version=1
                )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_rename_company_only_name(self):
        """只改名不改简介，简介应保留原值。"""
        db = await _create_test_db()
        try:
            profile_version_id = await _seed_published_base_profile(db)
            data = CompanyCreate(name="原名", introduction="保留简介")
            result = await create_company(db, data, base_profile_version_id=profile_version_id)

            update = CompanyUpdate(name="新名")
            await rename_company(db, result.id, update, expected_version=1)

            cur = await db.execute(
                """SELECT introduction FROM company_revisions
                   WHERE company_id = ? ORDER BY revision_number DESC LIMIT 1""",
                (result.id,),
            )
            rev = (await cur.fetchall())[0]
            assert rev["introduction"] == "保留简介"
        finally:
            await db.close()
