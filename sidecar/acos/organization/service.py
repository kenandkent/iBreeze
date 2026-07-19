"""组织服务 - Company 生命周期管理。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.organization.models import Company
from acos.rpc.errors import (
    ORG_COMPANY_DISSOLVED,
    ORG_NOT_FOUND,
    ORG_STATE_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    create_error,
)


class OrganizationService:
    """组织服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_company(row: aiosqlite.Row) -> Company:
        return Company(
            company_id=row["company_id"],
            name=row["name"],
            status=row["status"],
            root_department_id=row["root_department_id"],
            default_provider_policy=json.loads(row["default_provider_policy"]),
            default_budget_policy=json.loads(row["default_budget_policy"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
        )

    async def create_company(self, name: str, owner_id: str) -> Company:
        """创建公司（原子操作），初始为 initializing，待 activate 转 active。"""
        import uuid as _uuid
        from acos.events.outbox import OutboxWriter

        company = Company(name=name, status="initializing")
        now = self._now()
        company.created_at = now
        company.updated_at = now

        dept_id = str(uuid.uuid4())
        company.root_department_id = dept_id
        outbox = OutboxWriter()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            try:
                await db.execute(
                    """INSERT INTO companies
                       (company_id, name, status, root_department_id,
                        default_provider_policy, default_budget_policy,
                        created_at, updated_at, version)
                       VALUES (?, ?, ?, ?, '{}', '{}', ?, ?, 1)""",
                    (company.company_id, company.name, company.status,
                     dept_id, now, now),
                )

                await db.execute(
                    """INSERT INTO departments
                       (department_id, company_id, parent_department_id, name,
                        status, created_at, updated_at, version)
                       VALUES (?, ?, NULL, '总经理办公室', 'active', ?, ?, 1)""",
                    (dept_id, company.company_id, now, now),
                )

                await db.execute(
                    """INSERT INTO department_closure
                       (company_id, ancestor_department_id, descendant_department_id, depth)
                       VALUES (?, ?, ?, 0)""",
                    (company.company_id, dept_id, dept_id),
                )

                for table in ("knowledge_policies", "embedding_policies", "security_policies"):
                    await db.execute(
                        f"""INSERT INTO {table}
                            (policy_id, company_id, version, status, config, created_at)
                            VALUES (?, ?, 1, 'active', '{{}}', ?)""",
                        (str(uuid.uuid4()), company.company_id, now),
                    )

                await db.execute(
                    """INSERT INTO org_change_audit
                       (id, company_id, aggregate_type, aggregate_id, action,
                        before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                       VALUES (?, ?, 'company', ?, 'create', '', ?, ?, '', ?, ?)""",
                    (
                        str(uuid.uuid4()), company.company_id, company.company_id,
                        json.dumps({"name": company.name, "status": company.status}),
                        owner_id, str(uuid.uuid4()), now,
                    ),
                )

                trace_id = str(_uuid.uuid4())
                await outbox.emit_event(
                    db, company.company_id, "CompanyCreated",
                    "company", company.company_id, 1,
                    {"name": company.name, "root_department_id": dept_id},
                    trace_id, "local_owner", owner_id,
                    ["org_state_machine", "backend_bootstrap"],
                )

                await db.commit()
            except Exception:
                await db.rollback()
                raise

        return company

    async def get_company(self, company_id: str) -> Optional[Company]:
        """获取公司。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ? AND deleted_at IS NULL",
                (company_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_company(row)

    async def activate_company(self, company_id: str, expected_version: int, owner_id: str = "owner-1") -> Company:
        """激活公司。

        同事务完成：
        1. BackendBootstrapGate（CAS initializing→active）
        2. 创建首任员工（owner_id）到根部门
        3. 回填 root_department.leader_employee_id
        4. 写入 EmployeeCreated / DepartmentLeaderChanged / CompanyActivated 三事件
        """
        import uuid as _uuid
        from acos.events.outbox import OutboxWriter

        now = self._now()
        outbox = OutboxWriter()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. CAS 激活
            cursor = await db.execute(
                """UPDATE companies
                   SET status = 'active', version = version + 1, updated_at = ?
                   WHERE company_id = ? AND version = ?
                     AND status = 'initializing' AND deleted_at IS NULL""",
                (now, company_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法激活公司 {company_id}")

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            company_row = await cursor.fetchone()
            root_dept_id = company_row["root_department_id"]
            new_company_version = company_row["version"]

            # 2. 创建首任员工（owner）
            employee_id = str(_uuid.uuid4())
            employee_name = f"owner-{company_id[:8]}"
            await db.execute(
                """INSERT INTO employees
                   (employee_id, company_id, department_id, template_id,
                    capability_snapshot, name, role_name, employee_type,
                    reports_to_employee_id, stability_level, status,
                    session_transfer_state, primary_session_thread_id,
                    version, created_at, updated_at)
                   VALUES (?, ?, ?, '', '{}', ?, '创始人', 'company_leader',
                           NULL, 10, 'created', 'none', NULL, 1, ?, ?)""",
                (employee_id, company_id, root_dept_id, employee_name, now, now),
            )

            # 汇报链闭包表：自引用
            await db.execute(
                """INSERT INTO employee_reporting_closure
                   (company_id, ancestor_employee_id, descendant_employee_id, depth)
                   VALUES (?, ?, ?, 0)""",
                (company_id, employee_id, employee_id),
            )

            # 3. 回填 root_department.leader_employee_id
            await db.execute(
                "UPDATE departments SET leader_employee_id = ? WHERE department_id = ?",
                (employee_id, root_dept_id),
            )

            # 4. 写审计
            await db.execute(
                """INSERT INTO org_change_audit
                   (id, company_id, aggregate_type, aggregate_id, action,
                    before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                   VALUES (?, ?, 'company', ?, 'activate', ?, ?, ?, '', ?, ?)""",
                (
                    str(_uuid.uuid4()), company_id, company_id,
                    json.dumps({"status": "initializing"}),
                    json.dumps({"status": "active"}),
                    owner_id, str(_uuid.uuid4()), now,
                ),
            )

            trace_id = str(_uuid.uuid4())

            # 5. 三事件 via Outbox
            await outbox.emit_event(
                db, company_id, "CompanyActivated",
                "company", company_id, new_company_version,
                {"status": "active", "root_department_id": root_dept_id},
                trace_id, "local_owner", owner_id,
                ["org_state_machine"],
            )
            await outbox.emit_event(
                db, company_id, "EmployeeCreated",
                "employee", employee_id, 1,
                {"department_id": root_dept_id, "employee_type": "company_leader", "name": employee_name},
                trace_id, "local_owner", owner_id,
                ["employee_lifecycle"],
            )
            await outbox.emit_event(
                db, company_id, "DepartmentLeaderChanged",
                "department", root_dept_id, 1,
                {"leader_employee_id": employee_id},
                trace_id, "local_owner", owner_id,
                ["org_state_machine"],
            )

            await db.commit()

        return Company(
            company_id=company_id,
            name=company_row["name"],
            status="active",
            root_department_id=root_dept_id,
            default_provider_policy=json.loads(company_row["default_provider_policy"]),
            default_budget_policy=json.loads(company_row["default_budget_policy"]),
            created_at=company_row["created_at"],
            updated_at=now,
            version=new_company_version,
        )

    async def start_dissolution(
        self, company_id: str, expected_version: int, operator: str
    ) -> Company:
        """开始解散。"""
        import uuid as _uuid
        from acos.events.outbox import OutboxWriter

        now = self._now()
        outbox = OutboxWriter()
        consumers = ["organization", "task", "session", "knowledge", "provider", "backend"]

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE companies
                   SET status = 'dissolving', version = version + 1, updated_at = ?
                   WHERE company_id = ? AND version = ?
                     AND status = 'active' AND deleted_at IS NULL""",
                (now, company_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法解散公司 {company_id}")

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            row = await cursor.fetchone()
            new_version = row["version"]

            # 创建 watermark 表 + 初始化 6 个消费者 pending 行
            await db.execute(
                """CREATE TABLE IF NOT EXISTS dissolution_watermarks (
                    company_id TEXT NOT NULL,
                    consumer_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    completed_at TEXT,
                    error_detail TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (company_id, consumer_name)
                )"""
            )
            for consumer in consumers:
                await db.execute(
                    """INSERT OR IGNORE INTO dissolution_watermarks
                       (company_id, consumer_name, status, created_at, updated_at)
                       VALUES (?, ?, 'pending', ?, ?)""",
                    (company_id, consumer, now, now),
                )

            # 写审计
            await db.execute(
                """INSERT INTO org_change_audit
                   (id, company_id, aggregate_type, aggregate_id, action,
                    before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                   VALUES (?, ?, 'company', ?, 'start_dissolution', ?, ?, ?, '', ?, ?)""",
                (
                    str(_uuid.uuid4()), company_id, company_id,
                    json.dumps({"status": "active"}),
                    json.dumps({"status": "dissolving"}),
                    operator, str(_uuid.uuid4()), now,
                ),
            )

            # 发射 CompanyDissolutionStarted 事件
            trace_id = str(_uuid.uuid4())
            await outbox.emit_event(
                db, company_id, "CompanyDissolutionStarted",
                "company", company_id, new_version,
                {"status": "dissolving"},
                trace_id, "local_owner", operator,
                consumers,
            )

            await db.commit()
            return self._row_to_company(row)

    async def complete_dissolution(self, company_id: str) -> Company:
        """完成解散。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE companies
                   SET status = 'dissolved', version = version + 1, updated_at = ?
                   WHERE company_id = ? AND status = 'dissolving' AND deleted_at IS NULL""",
                (now, company_id),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法完成解散 {company_id}")

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_company(row)

    async def set_leader(
        self,
        department_id: str,
        employee_id: str,
        company_id: str,
        operator: str,
        expected_version: int,
    ) -> dict:
        """设置部门负责人（唯一事实源）。

        校验：
        1. 员工存在、active、属于该部门
        2. 同事务更新 department.leader_employee_id
        3. 派生 employee_type（公司根部门→company_leader，其余→department_leader）
        4. 写 DepartmentLeaderChanged 事件 + org_change_audit
        """
        import uuid as _uuid
        from acos.events.outbox import OutboxWriter

        now = self._now()
        outbox = OutboxWriter()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # 获取部门
            cursor = await db.execute(
                "SELECT * FROM departments WHERE department_id = ? AND company_id = ?",
                (department_id, company_id),
            )
            dept_row = await cursor.fetchone()
            if dept_row is None:
                raise create_error(ORG_NOT_FOUND, f"部门 {department_id} 不存在")

            # 获取员工
            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND company_id = ?",
                (employee_id, company_id),
            )
            emp_row = await cursor.fetchone()
            if emp_row is None:
                raise create_error(ORG_NOT_FOUND, f"员工 {employee_id} 不存在")
            if emp_row["status"] != "active":
                raise create_error(ORG_STATE_INVALID, f"员工 {employee_id} 非 active 状态，不可任命为负责人")
            if emp_row["department_id"] != department_id:
                raise create_error(
                    ORG_STATE_INVALID,
                    f"员工 {employee_id} 不属于部门 {department_id}",
                )

            # 判断是否为公司根部门
            cursor = await db.execute(
                "SELECT root_department_id FROM companies WHERE company_id = ?",
                (company_id,),
            )
            company_row = await cursor.fetchone()
            is_root = company_row["root_department_id"] == department_id
            new_emp_type = "company_leader" if is_root else "department_leader"

            old_leader_id = dept_row["leader_employee_id"]

            # 更新 department.leader_employee_id
            cursor = await db.execute(
                """UPDATE departments
                   SET leader_employee_id = ?, version = version + 1, updated_at = ?
                   WHERE department_id = ? AND company_id = ? AND version = ?""",
                (employee_id, now, department_id, company_id, dept_row["version"]),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: department {department_id}",
                )

            # 更新员工 employee_type
            cursor = await db.execute(
                """UPDATE employees
                   SET employee_type = ?, version = version + 1, updated_at = ?
                   WHERE employee_id = ? AND company_id = ? AND version = ?""",
                (new_emp_type, now, employee_id, company_id, emp_row["version"]),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: employee {employee_id}",
                )

            # 审计
            trace_id = str(_uuid.uuid4())
            before = {"leader_employee_id": old_leader_id, "employee_type": emp_row["employee_type"]}
            after = {"leader_employee_id": employee_id, "employee_type": new_emp_type}
            await db.execute(
                """INSERT INTO org_change_audit
                   (id, company_id, aggregate_type, aggregate_id, action,
                    before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                   VALUES (?, ?, 'department', ?, 'leader_changed', ?, ?, ?, '', ?, ?)""",
                (
                    str(_uuid.uuid4()), company_id, department_id,
                    json.dumps(before), json.dumps(after),
                    operator, trace_id, now,
                ),
            )

            # 事件
            dept_version = dept_row["version"] + 1
            await outbox.emit_event(
                db, company_id, "DepartmentLeaderChanged",
                "department", department_id, dept_version,
                {"leader_employee_id": employee_id, "old_leader_id": old_leader_id, "employee_type": new_emp_type},
                trace_id, "local_owner", operator,
                ["org_state_machine"],
            )

            await db.commit()

            return {
                "department_id": department_id,
                "leader_employee_id": employee_id,
                "employee_type": new_emp_type,
                "old_leader_id": old_leader_id,
            }

    async def update_company(
        self, company_id: str, expected_version: int, updates: dict
    ) -> Company:
        """更新公司（CAS）。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ? AND deleted_at IS NULL",
                (company_id,),
            )
            current = await cursor.fetchone()
            if current is None:
                raise create_error(ORG_NOT_FOUND, f"公司 {company_id} 不存在")
            if current["status"] == "dissolved":
                raise create_error(ORG_COMPANY_DISSOLVED, "已解散公司拒绝写入")

            allowed = {"name", "default_provider_policy", "default_budget_policy"}
            set_parts: list[str] = []
            params: list[object] = []
            for key, value in updates.items():
                if key not in allowed:
                    continue
                if key in ("default_provider_policy", "default_budget_policy"):
                    set_parts.append(f"{key} = ?")
                    params.append(json.dumps(value))
                else:
                    set_parts.append(f"{key} = ?")
                    params.append(value)

            if not set_parts:
                raise create_error(ORG_STATE_INVALID, "无可更新字段")

            set_parts.append("version = version + 1")
            set_parts.append("updated_at = ?")
            params.append(now)
            params.extend([company_id, expected_version])

            sql = f"""UPDATE companies
                      SET {', '.join(set_parts)}
                      WHERE company_id = ? AND version = ? AND deleted_at IS NULL"""
            cursor = await db.execute(sql, params)

            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: company {company_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_company(row)
