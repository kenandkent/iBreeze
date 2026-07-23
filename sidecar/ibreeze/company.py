"""公司领域服务——原子事务对齐 H.5。

创建公司时在同一 BEGIN IMMEDIATE 事务内按固定顺序写入：
Company + CompanyRevision + 总经理办公室 + DepartmentRevision +
固定职责 + 总经理 Employee + 公司会话 + 办公室会话。
任意失败全回滚，绝不返回部分对象。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    CompanyCreate,
    CompanyResponseDesignDoc,
    CompanyUpdate,
    CreatedByType,
    DepartmentType,
    WorkflowRole,
)
from ibreeze.state_machine import StateTransitionError


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _new_id() -> str:
    return str(uuid.uuid4()).replace("-", "")


async def _fetchall(cursor: Any) -> list[Any]:
    """兼容 sqlite3.Cursor 和 aiosqlite.Cursor 的 fetchall。"""
    result = cursor.fetchall()
    if hasattr(result, "__await__"):
        return await result
    return result


async def create_company(
    db: Any,
    data: CompanyCreate,
    *,
    base_profile_version_id: str,
) -> CompanyResponseDesignDoc:
    """H.5 公司创建原子事务。

    参数:
        db: aiosqlite 连接对象
        data: 公司创建请求
        base_profile_version_id: 已发布状态的底座版本 ID（必填）

    返回:
        CompanyResponseDesignDoc

    异常:
        ValueError: 名称重复、底座不存在或底座未发布
    """
    if not base_profile_version_id:
        raise ValueError("BASE_PROFILE_VERSION_REQUIRED")

    normalized_name = _normalize_name(data.name)
    now = _now_iso()

    # ── 1. 校验底座版本 published + 名称唯一性（事务外读取）─────────────
    cur = await db.execute(
        "SELECT id FROM employee_base_profile_versions WHERE id = ? AND status = 'published'",
        (base_profile_version_id,),
    )
    row = await _fetchall(cur)
    if not row:
        raise ValueError("BASE_PROFILE_NOT_PUBLISHED")

    cur = await db.execute(
        "SELECT id FROM companies WHERE normalized_name = ?",
        (normalized_name,),
    )
    row = await _fetchall(cur)
    if row:
        raise ValueError("NAME_EXISTS")

    # ── 2. 开启 BEGIN IMMEDIATE 事务 ──────────────────────────────────
    await db.execute("BEGIN IMMEDIATE")

    # ── 3. 设置 defer_foreign_keys=ON（仅 H.5 事务允许）────────────────
    fk_cur = await db.execute("PRAGMA defer_foreign_keys")
    fk_row = await _fetchall(fk_cur)
    current_fk = fk_row[0][0] if fk_row else 0
    if current_fk != 0:
        await db.execute("ROLLBACK")
        raise RuntimeError(
            "defer_foreign_keys is already ON — possible transaction boundary leak"
        )
    await db.execute("PRAGMA defer_foreign_keys = ON")

    try:
        # ── 3. 预生成全部 ID ────────────────────────────────────────────
        company_id = _new_id()
        company_revision_id = _new_id()
        office_id = _new_id()
        office_revision_id = _new_id()
        gm_employee_id = _new_id()
        company_conversation_id = _new_id()
        office_conversation_id = _new_id()
        office_responsibility_id = _new_id()

        # ── 4. 插入 Company ─────────────────────────────────────────────
        await db.execute(
            """INSERT INTO companies
               (id, normalized_name, current_revision_id,
                general_manager_office_id, general_manager_employee_id,
                company_conversation_id, status, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, 1)""",
            (
                company_id,
                normalized_name,
                company_revision_id,
                office_id,
                gm_employee_id,
                company_conversation_id,
                now,
                now,
            ),
        )

        # ── 5. 插入 CompanyRevision ─────────────────────────────────────
        revision_content = json.dumps(
            {"name": data.name, "introduction": data.introduction},
            ensure_ascii=False,
            sort_keys=True,
        )
        content_sha = _sha256(revision_content)

        await db.execute(
            """INSERT INTO company_revisions
               (id, company_id, revision_number, name, introduction,
                content_sha256, created_by_type, created_at)
               VALUES (?, ?, 1, ?, ?, ?, 'user', ?)""",
            (
                company_revision_id,
                company_id,
                data.name,
                data.introduction,
                content_sha,
                now,
            ),
        )

        # ── 6. 插入总经理办公室（Department）────────────────────────────
        office_normalized = _normalize_name("总经理办公室")
        await db.execute(
            """INSERT INTO departments
               (id, company_id, department_type, normalized_name,
                current_revision_id, leader_employee_id,
                department_conversation_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'general_manager_office', ?, ?, ?, ?, 'active', ?, ?, 1)""",
            (
                office_id,
                company_id,
                office_normalized,
                office_revision_id,
                gm_employee_id,
                office_conversation_id,
                now,
                now,
            ),
        )

        # ── 7. 插入办公室 DepartmentRevision ────────────────────────────
        office_rev_content = json.dumps(
            {"name": "总经理办公室", "function_description": "全局管理"},
            ensure_ascii=False,
            sort_keys=True,
        )
        office_content_sha = _sha256(office_rev_content)

        await db.execute(
            """INSERT INTO department_revisions
               (id, department_id, company_id, revision_number,
                name, function_description, content_sha256, created_at)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?)""",
            (
                office_revision_id,
                office_id,
                company_id,
                "总经理办公室",
                "全局管理",
                office_content_sha,
                now,
            ),
        )

        # ── 8. 插入固定职责（general_management）────────────────────────
        await db.execute(
            """INSERT INTO department_responsibilities
               (id, department_id, company_id, responsibility_key,
                name, description, accepted_task_types_json,
                required_capability_tags_json, deliverable_types_json,
                quality_gates_json, upstream_keys_json, downstream_keys_json,
                created_at, updated_at)
               VALUES (?, ?, ?, 'general_management', '全局管理', '统筹管理所有部门',
                       '[]', '[]', '[]', '[]', '[]', '[]', ?, ?)""",
            (office_responsibility_id, office_id, company_id, now, now),
        )

        # ── 9. 插入总经理 Employee ──────────────────────────────────────
        gm_display = "总经理"
        gm_normalized = _normalize_name(gm_display)
        await db.execute(
            """INSERT INTO employees
               (id, company_id, department_id, display_name,
                normalized_display_name, base_profile_version_id,
                workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'general_manager', 'active', ?, ?, 1)""",
            (
                gm_employee_id,
                company_id,
                office_id,
                gm_display,
                gm_normalized,
                base_profile_version_id,
                now,
                now,
            ),
        )

        # ── 10. 插入公司级 Conversation ─────────────────────────────────
        await db.execute(
            """INSERT INTO conversations
               (id, company_id, conversation_type, department_id, status, created_at)
               VALUES (?, ?, 'company', NULL, 'active', ?)""",
            (company_conversation_id, company_id, now),
        )

        # ── 11. 插入办公室级 Conversation ───────────────────────────────
        await db.execute(
            """INSERT INTO conversations
               (id, company_id, conversation_type, department_id, status, created_at)
               VALUES (?, ?, 'department', ?, 'active', ?)""",
            (office_conversation_id, company_id, office_id, now),
        )

        # ── 12. 验证六项不变量 ─────────────────────────────────────────
        # 不变量 1: current CompanyRevision 属于本公司
        cur = await db.execute(
            "SELECT id FROM company_revisions WHERE id = ? AND company_id = ?",
            (company_revision_id, company_id),
        )
        assert await _fetchall(cur), "invariant 1 failed: current revision does not belong to company"

        # 不变量 2: 恰有一个 active general_manager_office
        cur = await db.execute(
            """SELECT id FROM departments
               WHERE company_id = ? AND department_type = 'general_manager_office'
               AND status = 'active'""",
            (company_id,),
        )
        office_rows = await _fetchall(cur)
        assert len(office_rows) == 1, (
            f"invariant 2 failed: expected 1 active GM office, got {len(office_rows)}"
        )

        # 不变量 3: 总经理 Employee 属于该办公室且角色为 general_manager
        cur = await db.execute(
            """SELECT id FROM employees
               WHERE id = ? AND company_id = ? AND department_id = ?
               AND workflow_role = 'general_manager'""",
            (gm_employee_id, company_id, office_id),
        )
        assert await _fetchall(cur), "invariant 3 failed: GM employee not in office or wrong role"

        # 不变量 4: 办公室 leader_employee_id 等于总经理
        cur = await db.execute(
            """SELECT leader_employee_id FROM departments
               WHERE id = ? AND company_id = ?""",
            (office_id, company_id),
        )
        leader_rows = await _fetchall(cur)
        assert leader_rows and leader_rows[0][0] == gm_employee_id, (
            "invariant 4 failed: office leader != GM employee"
        )

        # 不变量 5: 公司会话类型为 company 且 department_id 为 null
        cur = await db.execute(
            """SELECT id FROM conversations
               WHERE id = ? AND company_id = ? AND conversation_type = 'company'
               AND department_id IS NULL""",
            (company_conversation_id, company_id),
        )
        assert await _fetchall(cur), "invariant 5 failed: company conversation invalid"

        # 不变量 6: 办公室会话类型为 department 且 department_id = office
        cur = await db.execute(
            """SELECT id FROM conversations
               WHERE id = ? AND company_id = ? AND conversation_type = 'department'
               AND department_id = ?""",
            (office_conversation_id, company_id, office_id),
        )
        assert await _fetchall(cur), "invariant 6 failed: office conversation invalid"

        # ── 13. 写 DomainEvent + Outbox ─────────────────────────────────
        event_id = _new_id()
        event_payload = json.dumps(
            {
                "company_id": company_id,
                "name": data.name,
                "introduction": data.introduction,
            },
            ensure_ascii=False,
        )
        trace_id = _new_id()

        await db.execute(
            """INSERT INTO domain_events
               (event_id, company_id, aggregate_type, aggregate_id,
                aggregate_version, event_type, payload_json,
                trace_id, occurred_at)
               VALUES (?, ?, 'company', ?, 1, 'company.created', ?, ?, ?)""",
            (event_id, company_id, company_id, event_payload, trace_id, now),
        )

        await db.execute(
            """INSERT INTO outbox_events
               (id, domain_event_id, topic, payload_json, status,
                attempts, next_attempt_at, created_at)
               VALUES (?, ?, 'company.created', ?, 'pending', 0, ?, ?)""",
            (_new_id(), event_id, event_payload, now, now),
        )

        # ── 14. 提交 ───────────────────────────────────────────────────
        await db.commit()

        return CompanyResponseDesignDoc(
            id=company_id,
            normalized_name=normalized_name,
            current_revision_id=company_revision_id,
            general_manager_office_id=office_id,
            general_manager_employee_id=gm_employee_id,
            company_conversation_id=company_conversation_id,
            status="active",
            created_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
            version=1,
        )

    except Exception:
        await db.rollback()
        raise
    finally:
        # ── 15. 断言 defer_foreign_keys 恢复 OFF ────────────────────────
        fk_cur = await db.execute("PRAGMA defer_foreign_keys")
        fk_after = await _fetchall(fk_cur)
        fk_val = fk_after[0][0] if fk_after else 0
        if fk_val != 0:
            await db.execute("PRAGMA defer_foreign_keys = OFF")
            raise RuntimeError(
                "defer_foreign_keys was not restored to OFF after transaction"
            )


async def rename_company(
    db: Any,
    company_id: str,
    data: CompanyUpdate,
    *,
    expected_version: int,
) -> CompanyResponseDesignDoc:
    """H.5 公司改名原子事务。

    同一 BEGIN IMMEDIATE 事务内：按 expected_version 锁定当前事实、
    生成新 Revision、更新 current_revision_id 与 normalized_name、
    递增聚合 version、写 DomainEvent 和 Outbox。
    """
    now = _now_iso()
    normalized_name = _normalize_name(data.name) if data.name else None

    # ── 开启 BEGIN IMMEDIATE 事务 ──────────────────────────────────────
    await db.execute("BEGIN IMMEDIATE")

    # ── 设置 defer_foreign_keys ──────────────────────────────────────────
    await db.execute("PRAGMA defer_foreign_keys = ON")

    try:
        # ── 按 expected_version 锁定当前公司 ────────────────────────────
        cur = await db.execute(
            """SELECT id, version, current_revision_id, normalized_name
               FROM companies WHERE id = ? AND version = ?""",
            (company_id, expected_version),
        )
        row = (await _fetchall(cur))[0:1]
        if not row:
            raise ValueError("VERSION_CONFLICT")

        current_version = row[0][1]
        current_rev_id = row[0][2]

        # ── 名称唯一性校验 ──────────────────────────────────────────────
        if normalized_name:
            cur = await db.execute(
                "SELECT id FROM companies WHERE normalized_name = ? AND id != ?",
                (normalized_name, company_id),
            )
            dup = await _fetchall(cur)
            if dup:
                raise ValueError("NAME_EXISTS")

        # ── 获取当前 revision 信息 ──────────────────────────────────────
        cur = await db.execute(
            "SELECT name, introduction FROM company_revisions WHERE id = ?",
            (current_rev_id,),
        )
        rev_row = (await _fetchall(cur))[0:1]
        old_name = rev_row[0][0]
        old_intro = rev_row[0][1]

        new_name = data.name if data.name else old_name
        new_intro = data.introduction if data.introduction else old_intro
        new_norm = _normalize_name(new_name)

        # ── 创建新 Revision ─────────────────────────────────────────────
        new_rev_id = _new_id()
        rev_content = json.dumps(
            {"name": new_name, "introduction": new_intro},
            ensure_ascii=False,
            sort_keys=True,
        )
        content_sha = _sha256(rev_content)

        await db.execute(
            """INSERT INTO company_revisions
               (id, company_id, revision_number, name, introduction,
                content_sha256, created_by_type, created_at)
               VALUES (?, ?, (SELECT COALESCE(MAX(revision_number), 0) + 1
                              FROM company_revisions WHERE company_id = ?),
                       ?, ?, ?, 'user', ?)""",
            (new_rev_id, company_id, company_id, new_name, new_intro, content_sha, now),
        )

        # ── 更新聚合：current_revision_id + normalized_name + version ──
        new_version = current_version + 1
        await db.execute(
            """UPDATE companies
               SET current_revision_id = ?, normalized_name = ?,
                   version = ?, updated_at = ?
               WHERE id = ? AND version = ?""",
            (new_rev_id, new_norm, new_version, now, company_id, current_version),
        )

        # ── 写 DomainEvent + Outbox ─────────────────────────────────────
        event_id = _new_id()
        event_payload = json.dumps(
            {
                "company_id": company_id,
                "old_name": old_name,
                "new_name": new_name,
            },
            ensure_ascii=False,
        )
        trace_id = _new_id()

        await db.execute(
            """INSERT INTO domain_events
               (event_id, company_id, aggregate_type, aggregate_id,
                aggregate_version, event_type, payload_json,
                trace_id, occurred_at)
               VALUES (?, ?, 'company', ?, ?, 'company.renamed', ?, ?, ?)""",
            (event_id, company_id, company_id, new_version, event_payload, trace_id, now),
        )

        await db.execute(
            """INSERT INTO outbox_events
               (id, domain_event_id, topic, payload_json, status,
                attempts, next_attempt_at, created_at)
               VALUES (?, ?, 'company.renamed', ?, 'pending', 0, ?, ?)""",
            (_new_id(), event_id, event_payload, now, now),
        )

        await db.commit()

        return CompanyResponseDesignDoc(
            id=company_id,
            normalized_name=new_norm,
            current_revision_id=new_rev_id,
            general_manager_office_id="",
            general_manager_employee_id="",
            company_conversation_id="",
            status="active",
            created_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
            version=new_version,
        )

    except Exception:
        await db.rollback()
        raise
    finally:
        fk_cur = await db.execute("PRAGMA defer_foreign_keys")
        fk_after = await _fetchall(fk_cur)
        fk_val = fk_after[0][0] if fk_after else 0
        if fk_val != 0:
            await db.execute("PRAGMA defer_foreign_keys = OFF")
