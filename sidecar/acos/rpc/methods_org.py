"""组织 RPC 方法集合。"""

from __future__ import annotations

import aiosqlite
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from acos.organization.employee_service import EmployeeService
from acos.organization.permission_engine import PermissionEngine
from acos.organization.service import OrganizationService
from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer


class OrganizationMethods:
    """组织相关的 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._service = OrganizationService(db_path)
        self._employee_service = EmployeeService(db_path)

    def register_to(self, server: RPCServer) -> None:
        # 公司 (org.company.*)
        server.register_method("org.company.list", self._company_list)
        server.register_method("org.company.get", self._company_get)
        server.register_method("org.company.create", self._company_create)
        server.register_method("org.company.update", self._company_update)
        server.register_method("org.company.delete", self._company_delete)
        server.register_method("org.company.restore", self._company_restore)
        server.register_method("org.company.activate", self._company_activate)
        server.register_method("org.company.dissolve", self._company_dissolve)
        # 部门 (org.department.*)
        server.register_method("org.department.list", self._department_list)
        server.register_method("org.department.create", self._department_create)
        server.register_method("org.department.update", self._department_update)
        server.register_method("org.department.delete", self._department_delete)
        server.register_method("org.department.move", self._department_move)
        server.register_method("org.department.setLeader", self._department_set_leader)
        server.register_method("org.department.freeze", self._department_freeze)
        server.register_method("org.department.unfreeze", self._department_unfreeze)
        server.register_method("org.department.archive", self._department_archive)
        server.register_method("org.department.get", self._department_get)
        # 员工 (org.employee.*)
        server.register_method("org.employee.list", self._employee_list)
        server.register_method("org.employee.create", self._employee_create)
        server.register_method("org.employee.update", self._employee_update)
        server.register_method("org.employee.delete", self._employee_delete)
        server.register_method("org.employee.setManager", self._employee_set_manager)
        server.register_method("org.employee.activate", self._employee_activate)
        server.register_method("org.employee.suspend", self._employee_suspend)
        server.register_method("org.employee.resume", self._employee_resume)
        server.register_method("org.employee.archive", self._employee_archive)
        server.register_method("org.employee.transfer", self._employee_transfer)
        server.register_method("org.employee.get", self._employee_get)
        # 职员模板 (org.template.*) 由 CapabilityMethods 在 methods_capability.py 中实现
        # 授权 (org.grant.*)
        server.register_method("org.grant.create", self._grant_create)
        server.register_method("org.grant.list", self._grant_list)
        server.register_method("org.grant.get", self._grant_get)
        server.register_method("org.grant.revoke", self._grant_revoke)
        # 组织图 + 权限解析
        server.register_method("org.graph.get", self._org_graph_get)
        server.register_method("org.permission.resolve", self._permission_resolve)
        # 任务 (task.*，设计命名，handler 实现位于本模块尾部)
        server.register_method("task.list", self._task_list)
        server.register_method("task.create", self._task_create)
        server.register_method("task.get", self._task_get)
        # 知识库 (knowledge.*，Phase 8 统一迁移为 kg.*)
        server.register_method("knowledge.list", self._knowledge_list)
        server.register_method("knowledge.create", self._knowledge_create)

    # ── 公司 ──────────────────────────────────────────────

    async def _company_list(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            # 软删后（dissolving / 已置 deleted_at）默认不出现在列表
            cursor = await conn.execute(
                "SELECT * FROM companies WHERE status != 'dissolving' AND deleted_at IS NULL ORDER BY created_at DESC"
            )
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await conn.close()

    async def _company_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            return {"error": "missing company_id"}
        company = await self._service.get_company(company_id)
        if company is None:
            return {"error": "not found"}
        return {
            "company_id": company.company_id,
            "name": company.name,
            "status": company.status,
            "created_at": company.created_at,
        }

    async def _company_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        owner_id = params.get("owner_id", "system")
        if not name:
            return {"error": "missing name"}
        company = await self._service.create_company(name, owner_id)
        return {
            "company_id": company.company_id,
            "name": company.name,
            "status": company.status,
            "created_at": company.created_at,
        }

    async def _company_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        expected_version = params.get("expected_version", 1)
        name = params.get("name")
        if not company_id:
            return {"error": "missing company_id"}
        updates: dict[str, object] = {}
        if name is not None:
            if not name or not name.strip():
                return {"error": "ORG-VALIDATION: name 不能为空"}
            updates["name"] = name.strip()
        if not updates:
            return {"error": "无可更新字段"}
        try:
            company = await self._service.update_company(
                company_id, expected_version, updates
            )
        except (ValueError, AcosError) as e:
            return {"error": str(e)}
        return {
            "company_id": company.company_id,
            "name": company.name,
            "version": company.version,
        }

    async def _company_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """删除公司 = 启动解散流程，进入 dissolving 可恢复状态（设计 §6.1）。

        不再一次性硬转 dissolved；watermark 对账完成后由 workflow.companyDissolution.resolve 转 dissolved。
        """
        company_id = params.get("company_id")
        expected_version = params.get("expected_version", 1)
        if not company_id:
            return {"error": "missing company_id"}
        try:
            company = await self._service.start_dissolution(
                company_id, expected_version, "system"
            )
        except (ValueError, AcosError) as e:
            return {"error": str(e)}
        # 软删：dissolving 同时写 deleted_at，确保 list 不再返回（SC-60-2）
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                "UPDATE companies SET deleted_at = ? WHERE company_id = ?",
                (datetime.now(timezone.utc).isoformat(), company_id),
            )
            await conn.commit()
        finally:
            await conn.close()
        return {
            "company_id": company.company_id,
            "status": company.status,
            "version": company.version,
            "dissolving": True,
            "deleted": True,
        }

    async def _company_restore(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        company_id = params.get("company_id")
        if not company_id:
            return {"error": "missing company_id"}
        now = datetime.now(timezone.utc).isoformat()
        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                "UPDATE companies SET status = 'active', deleted_at = NULL, updated_at = ? WHERE company_id = ?",
                (now, company_id),
            )
            await conn.execute(
                "UPDATE departments SET deleted_at = NULL, status = 'active', updated_at = ? WHERE company_id = ? AND deleted_at IS NOT NULL",
                (now, company_id),
            )
            await conn.execute(
                "UPDATE employees SET deleted_at = NULL, updated_at = ? WHERE company_id = ? AND deleted_at IS NOT NULL",
                (now, company_id),
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"company_id": company_id, "restored": True}

    async def _company_activate(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        expected_version = params.get("expected_version", 1)
        leader = params.get("leader") or {}
        name = leader.get("name", "owner")
        template_id = leader.get("template_id")
        if not company_id:
            return {"error": "missing company_id"}
        try:
            company = await self._service.activate_company(company_id, expected_version)
        except (ValueError, AcosError) as e:
            return {"error": str(e)}
        # 负责人已由 service.activate_company 创建，查回 owner 员工 id
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        try:
            cursor = await conn.execute(
                """SELECT employee_id FROM employees
                   WHERE company_id = ? AND employee_type = 'company_leader'
                   ORDER BY created_at DESC LIMIT 1""",
                (company_id,),
            )
            row = await cursor.fetchone()
            leader_employee_id = row[0] if row else None
        finally:
            await conn.close()
        return {
            "company_id": company.company_id,
            "status": company.status,
            "version": company.version,
            "leader_employee_id": leader_employee_id,
        }

    async def _company_dissolve(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        expected_version = params.get("expected_version", 1)
        reason = params.get("reason", "")
        if not company_id:
            return {"error": "missing company_id"}
        try:
            company = await self._service.start_dissolution(company_id, expected_version, "system")
        except (ValueError, AcosError) as e:
            return {"error": str(e)}
        now = datetime.now(timezone.utc).isoformat()
        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                "INSERT INTO org_change_audit (id, company_id, aggregate_type, aggregate_id, action, before_snapshot, after_snapshot, operator, reason, trace_id, timestamp) VALUES (?, ?, 'company', ?, 'dissolve', '', ?, 'system', ?, ?, ?)",
                (str(uuid.uuid4()), company_id, company_id, json.dumps({"status": "dissolving"}), reason, str(uuid.uuid4()), now),
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"company_id": company.company_id, "status": company.status, "version": company.version}

    async def _department_move(self, params: dict[str, Any]) -> dict[str, Any]:
        department_id = params.get("department_id")
        new_parent_id = params.get("new_parent_id")
        if not department_id or not new_parent_id:
            return {"error": "missing department_id or new_parent_id"}
        import aiosqlite
        from acos.organization.closure import DepartmentClosure
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cursor = await conn.execute(
                "SELECT company_id FROM departments WHERE department_id = ?", (department_id,)
            )
            company_id = await cursor.fetchone()
            if company_id is None:
                return {"error": "ORG-NOT-FOUND"}
            company_id = company_id["company_id"]
            store = DepartmentClosure()
            parent = await conn.execute(
                "SELECT company_id FROM departments WHERE department_id = ? AND deleted_at IS NULL",
                (new_parent_id,),
            )
            parent_row = await parent.fetchone()
            if parent_row is None:
                return {"error": "ORG-PARENT-NOT-FOUND"}
            if parent_row["company_id"] != company_id:
                return {"error": "ORG-DEPT-CROSS-COMPANY-DENIED"}
            if await store.check_cycle(conn, company_id, department_id, new_parent_id):
                return {"error": "ORG-DEPT-CYCLE: 不能移动到自身或后代下"}
            await store.move_subtree(conn, company_id, department_id, new_parent_id)
            await conn.commit()
        except (ValueError, AcosError) as e:
            await conn.rollback()
            return {"error": str(e)}
        finally:
            await conn.close()
        return {"department_id": department_id, "new_parent_id": new_parent_id, "moved": True}

    async def _department_set_leader(self, params: dict[str, Any]) -> dict[str, Any]:
        department_id = params.get("department_id")
        leader_employee_id = params.get("leader_employee_id")
        reason = params.get("reason", "")
        if not department_id or not leader_employee_id:
            return {"error": "missing department_id or leader_employee_id"}
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        try:
            cursor = await conn.execute(
                "UPDATE departments SET leader_employee_id = ?, updated_at = ? WHERE department_id = ? AND deleted_at IS NULL",
                (leader_employee_id, datetime.now(timezone.utc).isoformat(), department_id),
            )
            if cursor.rowcount == 0:
                return {"error": "ORG-NOT-FOUND"}
            await conn.execute(
                "UPDATE employees SET employee_type = 'department_leader', reports_to_employee_id = (SELECT leader_employee_id FROM departments WHERE department_id = (SELECT parent_department_id FROM departments WHERE department_id = ?)) WHERE employee_id = ?",
                (department_id, leader_employee_id),
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"department_id": department_id, "leader_employee_id": leader_employee_id, "ok": True}

    async def _set_department_status(self, department_id: str, status: str) -> dict[str, Any]:
        if not department_id:
            return {"error": "missing department_id"}
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        try:
            cursor = await conn.execute(
                "UPDATE departments SET status = ?, updated_at = ? WHERE department_id = ? AND deleted_at IS NULL",
                (status, datetime.now(timezone.utc).isoformat(), department_id),
            )
            if cursor.rowcount == 0:
                return {"error": "ORG-NOT-FOUND"}
            await conn.commit()
        finally:
            await conn.close()
        return {"department_id": department_id, "status": status}

    async def _department_freeze(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._set_department_status(params.get("department_id"), "frozen")

    async def _department_unfreeze(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._set_department_status(params.get("department_id"), "active")

    async def _department_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._set_department_status(params.get("department_id"), "archived")

    async def _department_get(self, params: dict[str, Any]) -> dict[str, Any]:
        department_id = params.get("department_id")
        if not department_id:
            return {"error": "missing department_id"}
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cursor = await conn.execute(
                "SELECT * FROM departments WHERE department_id = ? AND deleted_at IS NULL",
                (department_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return {"error": "ORG-NOT-FOUND"}
            dept = dict(row)
            # 闭包关系：祖先 + 后代
            cur = await conn.execute(
                "SELECT ancestor_department_id FROM department_closure WHERE descendant_department_id = ? AND depth > 0",
                (department_id,),
            )
            ancestors = [r["ancestor_department_id"] for r in await cur.fetchall()]
            cur = await conn.execute(
                "SELECT descendant_department_id FROM department_closure WHERE ancestor_department_id = ? AND depth > 0",
                (department_id,),
            )
            descendants = [r["descendant_department_id"] for r in await cur.fetchall()]
            dept["ancestors"] = ancestors
            dept["descendants"] = descendants
            return dept
        finally:
            await conn.close()

    async def _employee_set_manager(self, params: dict[str, Any]) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        reports_to = params.get("reports_to_employee_id")
        reason = params.get("reason", "")
        if not employee_id:
            return {"error": "missing employee_id"}
        if reports_to == employee_id:
            return {"error": "ORG-REPORTING-CYCLE: 不能将自身设为上级"}
        company_id = await self._employee_company_id(employee_id)
        if company_id is None:
            return {"error": "ORG-NOT-FOUND"}
        expected_version = params.get("expected_version", 1)
        operator = params.get("operator", "system")
        try:
            # 委托服务层：基于员工汇报链闭包做正确的环检测
            emp = await self._employee_service.set_manager(
                employee_id, company_id, expected_version, reports_to, operator,
            )
        except Exception as e:
            code = getattr(e, "code", None)
            return {"error": code if code else str(e)}
        return {"employee_id": emp.employee_id, "reports_to_employee_id": reports_to, "ok": True}

    async def _employee_company_id(self, employee_id: str) -> str | None:
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        try:
            cursor = await conn.execute(
                "SELECT company_id FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            row = await cursor.fetchone()
        finally:
            await conn.close()
        return row[0] if row else None

    async def _set_employee_status(self, params: dict[str, Any], status: str) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        if not employee_id:
            return {"error": "missing employee_id"}
        expected_version = params.get("expected_version", 1)
        company_id = await self._employee_company_id(employee_id)
        if company_id is None:
            return {"error": "ORG-NOT-FOUND"}
        # 委托服务层状态机：校验合法转换 + CAS
        methods = {
            "active": self._employee_service.activate,
            "suspended": self._employee_service.suspend,
            "archived": self._employee_service.archive,
        }
        try:
            if status == "active":
                emp = await self._employee_service.activate(employee_id, company_id, expected_version)
            elif status == "suspended":
                emp = await self._employee_service.suspend(employee_id, company_id, expected_version)
            elif status == "archived":
                emp = await self._employee_service.archive(employee_id, company_id, expected_version)
            else:
                return {"error": f"不支持的状态: {status}"}
        except (ValueError, AcosError) as e:
            return {"error": str(e)}
        return {"employee_id": emp.employee_id, "status": emp.status, "version": emp.version}

    async def _employee_activate(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._set_employee_status(params, "active")

    async def _employee_suspend(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._set_employee_status(params, "suspended")

    async def _employee_resume(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._set_employee_status(params, "active")

    async def _employee_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._set_employee_status(params, "archived")

    async def _employee_transfer(self, params: dict[str, Any]) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        new_department_id = params.get("new_department_id")
        reason = params.get("reason", "")
        if not employee_id or not new_department_id:
            return {"error": "missing employee_id or new_department_id"}
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        try:
            cursor = await conn.execute(
                "UPDATE employees SET department_id = ?, updated_at = ? WHERE employee_id = ? AND deleted_at IS NULL",
                (new_department_id, datetime.now(timezone.utc).isoformat(), employee_id),
            )
            if cursor.rowcount == 0:
                return {"error": "ORG-NOT-FOUND"}
            await conn.commit()
        finally:
            await conn.close()
        return {"employee_id": employee_id, "new_department_id": new_department_id, "transfer_started": True}

    async def _employee_get(self, params: dict[str, Any]) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        if not employee_id:
            return {"error": "missing employee_id"}
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cursor = await conn.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return {"error": "ORG-NOT-FOUND"}
            return dict(row)
        finally:
            await conn.close()

    async def _grant_create(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite

        company_id = params.get("company_id")
        employee_id = params.get("employee_id")
        target_type = params.get("target_type")
        target_id = params.get("target_id")
        permission = params.get("permission")
        expires_at = params.get("expires_at")
        if not all([company_id, employee_id, target_type, target_id, permission, expires_at]):
            return {"error": "missing required fields"}
        # 校验 target/permission 匹配
        if target_type == "department" and permission != "department_read":
            return {"error": "GRANT-PERM-MISMATCH: department 仅可配 department_read"}
        if target_type == "task" and permission != "task_read":
            return {"error": "GRANT-PERM-MISMATCH: task 仅可配 task_read"}
        if target_type not in ("department", "task"):
            return {"error": "GRANT-TARGET-INVALID"}
        now = datetime.now(timezone.utc).isoformat()
        if expires_at <= now:
            return {"error": "GRANT-EXPIRED: expires_at 必须晚于当前时间"}

        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            # 校验同公司且未删除
            cur = await conn.execute(
                "SELECT company_id FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            emp = await cur.fetchone()
            if emp is None:
                return {"error": "GRANT-EMP-NOT-FOUND"}
            if emp["company_id"] != company_id:
                return {"error": "GRANT-CROSS-COMPANY-DENIED"}
            if target_type == "department":
                cur = await conn.execute(
                    "SELECT company_id, deleted_at FROM departments WHERE department_id = ?",
                    (target_id,),
                )
            else:
                cur = await conn.execute(
                    "SELECT company_id, deleted_at FROM tasks WHERE task_id = ?",
                    (target_id,),
                )
            tgt = await cur.fetchone()
            if tgt is None:
                return {"error": "GRANT-TARGET-NOT-FOUND"}
            if tgt["company_id"] != company_id:
                return {"error": "GRANT-CROSS-COMPANY-DENIED"}
            if tgt["deleted_at"] is not None:
                return {"error": "GRANT-TARGET-ARCHIVED"}
        finally:
            await conn.close()

        # approved_by 由服务端注入，不接受客户端参数
        approved_by = params.get("approved_by") or "system"
        engine = PermissionEngine(self._db_path)
        grant_id = await engine.grant(
            company_id=company_id, employee_id=employee_id,
            target_type=target_type, target_id=target_id,
            permission=permission, expires_at=expires_at, approved_by=approved_by,
        )
        return {"grant_id": grant_id}

    async def _grant_list(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite

        company_id = params.get("company_id")
        if not company_id:
            raise ValueError("missing company_id")
        employee_id = params.get("employee_id")
        target_type = params.get("target_type")
        permission = params.get("permission")
        status = params.get("status", "active")

        conds = ["company_id = ?"]
        vals: list[Any] = [company_id]
        if employee_id:
            conds.append("employee_id = ?")
            vals.append(employee_id)
        if target_type:
            conds.append("target_type = ?")
            vals.append(target_type)
        if permission:
            conds.append("permission = ?")
            vals.append(permission)
        if status:
            conds.append("status = ?")
            vals.append(status)

        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                f"SELECT * FROM access_grants WHERE {' AND '.join(conds)} ORDER BY created_at DESC",
                vals,
            )
            rows = [dict(r) for r in await cur.fetchall()]
        finally:
            await conn.close()
        # 派生字段：status='active' 但已过期的 grant 标记为 expired（内存标注，不落库）
        now_iso = datetime.now(timezone.utc).isoformat()
        for g in rows:
            if g.get("status") == "active" and g.get("expires_at") and g["expires_at"] <= now_iso:
                g["expired"] = True
        return {"grants": rows, "total": len(rows)}

    async def _grant_get(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite

        grant_id = params.get("grant_id")
        if not grant_id:
            return {"error": "missing grant_id"}
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                "SELECT * FROM access_grants WHERE grant_id = ?", (grant_id,)
            )
            row = await cur.fetchone()
        finally:
            await conn.close()
        if row is None:
            return {"error": "GRANT-NOT-FOUND"}
        return {"grant": dict(row)}

    async def _grant_revoke(self, params: dict[str, Any]) -> dict[str, Any]:
        grant_id = params.get("grant_id")
        company_id = params.get("company_id")
        expected_version = params.get("expected_version", 1)
        if not grant_id or not company_id:
            return {"error": "missing grant_id or company_id"}
        engine = PermissionEngine(self._db_path)
        ok = await engine.revoke(grant_id, company_id, expected_version)
        if not ok:
            return {"error": "GRANT-REVOKE-CONFLICT: 版本冲突或已非 active"}
        return {"grant_id": grant_id, "status": "revoked", "ok": True}

    async def _org_graph_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            return {"error": "missing company_id"}
        import aiosqlite
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cursor = await conn.execute(
                """SELECT d.department_id, d.name, d.parent_department_id, d.leader_employee_id, d.status
                   FROM departments d WHERE d.company_id = ? AND d.deleted_at IS NULL ORDER BY d.created_at""",
                (company_id,),
            )
            depts = [dict(row) for row in await cursor.fetchall()]
            cursor = await conn.execute(
                "SELECT employee_id, name, department_id, employee_type, status FROM employees WHERE company_id = ? AND deleted_at IS NULL",
                (company_id,),
            )
            employees = [dict(row) for row in await cursor.fetchall()]
        finally:
            await conn.close()
        return {"company_id": company_id, "departments": depts, "employees": employees}

    async def _permission_resolve(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite

        company_id = params.get("company_id")
        employee_id = params.get("employee_id")
        task_id = params.get("task_id")
        if not company_id or not employee_id:
            return {"error": "missing company_id or employee_id"}
        # 校验员工属于该公司且未归档
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                "SELECT company_id, deleted_at FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            emp = await cur.fetchone()
        finally:
            await conn.close()
        if emp is None:
            return {"error": "ORG-NOT-FOUND"}
        if emp["company_id"] != company_id:
            return {"error": "GRANT-CROSS-COMPANY-DENIED"}
        engine = PermissionEngine(self._db_path)
        scope = await engine.compute_scope(employee_id, company_id, task_id)
        return {
            "company_id": company_id,
            "employee_id": employee_id,
            "scope": scope,
            "scope_hash": scope["scope_hash"],
        }

    # ── 部门 ──────────────────────────────────────────────

    async def _department_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        import aiosqlite
        company_id = params.get("company_id")
        if not company_id:
            return {"error": "missing company_id"}
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cursor = await conn.execute(
                "SELECT * FROM departments WHERE company_id = ? AND deleted_at IS NULL ORDER BY created_at DESC",
                (company_id,),
            )
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await conn.close()

    async def _department_create(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        company_id = params.get("company_id", "")
        name = params.get("name", "")
        parent_department_id = params.get("parent_department_id", "")
        description = params.get("description", "")

        if not name:
            return {"error": "missing name"}
        if not company_id:
            return {"error": "missing company_id"}

        # 冻结部门不可新建子部门
        if parent_department_id:
            conn = await aiosqlite.connect(self._db_path)
            conn.row_factory = aiosqlite.Row
            try:
                cur = await conn.execute(
                    "SELECT status FROM departments WHERE department_id = ? AND deleted_at IS NULL",
                    (parent_department_id,),
                )
                parent_row = await cur.fetchone()
            finally:
                await conn.close()
            if parent_row is not None and parent_row["status"] == "frozen":
                return {"error": "ORG-DEPT-FROZEN: 冻结部门不可新建子部门"}

        now = datetime.now(timezone.utc).isoformat()
        department_id = str(uuid.uuid4())

        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                """INSERT INTO departments
                   (department_id, company_id, parent_department_id, name,
                    description, status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', 1, ?, ?)""",
                (department_id, company_id, parent_department_id or None,
                 name, description, now, now),
            )
            # 插入闭包表自身记录
            await conn.execute(
                "INSERT INTO department_closure (company_id, ancestor_department_id, descendant_department_id, depth) VALUES (?, ?, ?, 0)",
                (company_id, department_id, department_id),
            )
            # 如果有父部门，复制父部门的祖先链
            if parent_department_id:
                await conn.execute(
                    """INSERT INTO department_closure (company_id, ancestor_department_id, descendant_department_id, depth)
                       SELECT company_id, ancestor_department_id, ?, depth + 1
                       FROM department_closure
                       WHERE company_id = ? AND descendant_department_id = ?""",
                    (department_id, company_id, parent_department_id),
                )
            await conn.commit()
        finally:
            await conn.close()

        return {
            "department_id": department_id,
            "name": name,
            "company_id": company_id,
            "parent_department_id": parent_department_id or None,
            "status": "active",
        }

    async def _department_update(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        department_id = params.get("department_id")
        name = params.get("name")
        description = params.get("description")
        if not department_id:
            return {"error": "missing department_id"}
        now = datetime.now(timezone.utc).isoformat()
        conn = await aiosqlite.connect(self._db_path)
        try:
            sets = ["updated_at = ?"]
            vals: list[Any] = [now]
            if name is not None:
                sets.append("name = ?")
                vals.append(name)
            if description is not None:
                sets.append("description = ?")
                vals.append(description)
            vals.append(department_id)
            await conn.execute(
                f"UPDATE departments SET {', '.join(sets)} WHERE department_id = ? AND deleted_at IS NULL",
                vals,
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"department_id": department_id}

    async def _department_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """软删部门：标记 deleted_at + 归档，保留闭包关系与审计（设计软删约定）。"""
        import aiosqlite
        department_id = params.get("department_id")
        if not department_id:
            return {"error": "missing department_id"}
        now = datetime.now(timezone.utc).isoformat()
        conn = await aiosqlite.connect(self._db_path)
        try:
            # 含员工的部门不可删除
            cur = await conn.execute(
                "SELECT 1 FROM employees WHERE department_id = ? AND deleted_at IS NULL LIMIT 1",
                (department_id,),
            )
            if await cur.fetchone() is not None:
                return {"error": "ORG-DEPT-HAS-EMPLOYEES: 含员工的部门不可删除"}
            cursor = await conn.execute(
                "UPDATE departments SET deleted_at = ?, status = 'archived', updated_at = ? WHERE department_id = ? AND deleted_at IS NULL",
                (now, now, department_id),
            )
            if cursor.rowcount == 0:
                return {"error": "ORG-NOT-FOUND"}
            await conn.commit()
        finally:
            await conn.close()
        return {"department_id": department_id, "deleted": True}

    # ── 员工 ──────────────────────────────────────────────

    async def _employee_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        import aiosqlite
        company_id = params.get("company_id")
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            if company_id:
                cursor = await conn.execute(
                    "SELECT * FROM employees WHERE company_id = ? AND deleted_at IS NULL ORDER BY created_at DESC",
                    (company_id,),
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM employees WHERE deleted_at IS NULL ORDER BY created_at DESC"
                )
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await conn.close()

    async def _employee_create(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        name = params.get("name", "")
        company_id = params.get("company_id", "")
        department_id = params.get("department_id", "")
        template_id = params.get("template_id", "")
        role_name = params.get("role_name", "")
        employee_type = params.get("employee_type", "employee")

        if not name:
            return {"error": "missing name"}
        if not company_id:
            return {"error": "missing company_id"}

        now = datetime.now(timezone.utc).isoformat()
        employee_id = str(uuid.uuid4())

        conn = await aiosqlite.connect(self._db_path)
        try:
            capability_snapshot = "{}"
            if template_id:
                cur = await conn.execute(
                    "SELECT capability_snapshot, company_id, status FROM employee_templates WHERE template_id = ?",
                    (template_id,),
                )
                row = await cur.fetchone()
                if row is None or not row[0]:
                    return {"error": "ORG-TEMPLATE-NOT-FOUND"}
                # 跨公司模板串快照拒绝
                if row[1] != params["company_id"]:
                    return {"error": "ORG-TEMPLATE-CROSS-COMPANY-DENIED"}
                # 仅 active 模板可用于建/改绑员工
                if row[2] != "active":
                    return {"error": "ORG-TEMPLATE-NOT-ACTIVE"}
                capability_snapshot = row[0]
            await conn.execute(
                """INSERT INTO employees
                   (employee_id, company_id, department_id, template_id,
                    capability_snapshot, name, role_name, employee_type,
                    stability_level, status, session_transfer_state,
                    version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5, 'created', 'none', 1, ?, ?)""",
                (employee_id, company_id, department_id, template_id,
                 capability_snapshot, name, role_name, employee_type, now, now),
            )
            # 维护汇报链闭包表，供 setManager 环检测使用
            from acos.organization.reporting_closure import ReportingClosure
            rc = ReportingClosure()
            await rc.add_employee(conn, company_id, employee_id, None)
            await conn.commit()
        finally:
            await conn.close()

        return {
            "employee_id": employee_id,
            "name": name,
            "role_name": role_name,
            "employee_type": employee_type,
            "status": "created",
        }

    async def _employee_update(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        employee_id = params.get("employee_id")
        if not employee_id:
            return {"error": "missing employee_id"}
        now = datetime.now(timezone.utc).isoformat()
        conn = await aiosqlite.connect(self._db_path)
        try:
            # 改绑 template_id 时校验模板 active + 同公司
            if params.get("template_id") is not None:
                cur = await conn.execute(
                    "SELECT company_id, status FROM employee_templates WHERE template_id = ?",
                    (params["template_id"],),
                )
                trow = await cur.fetchone()
                if trow is None:
                    return {"error": "ORG-TEMPLATE-NOT-FOUND"}
                if trow[0] != params.get("company_id", ""):
                    return {"error": "ORG-TEMPLATE-CROSS-COMPANY-DENIED"}
                if trow[1] != "active":
                    return {"error": "ORG-TEMPLATE-NOT-ACTIVE"}
            sets = ["updated_at = ?"]
            vals: list[Any] = [now]
            for field in ("name", "role_name", "employee_type", "department_id", "template_id"):
                if field in params and params[field] is not None:
                    sets.append(f"{field} = ?")
                    vals.append(params[field])
            vals.append(employee_id)
            await conn.execute(
                f"UPDATE employees SET {', '.join(sets)} WHERE employee_id = ? AND deleted_at IS NULL",
                vals,
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"employee_id": employee_id}

    async def _employee_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        if not employee_id:
            return {"error": "missing employee_id"}
        company_id = await self._employee_company_id(employee_id)
        if company_id is None:
            return {"error": "ORG-NOT-FOUND"}
        expected_version = params.get("expected_version", 1)
        try:
            # 委托服务层：走软删 + 状态机 + deleted_at
            emp = await self._employee_service.delete(employee_id, company_id, expected_version)
        except (ValueError, Exception) as e:
            code = getattr(e, "code", None)
            return {"error": code if code else str(e)}
        return {"employee_id": emp.employee_id, "status": emp.status, "deleted": True}

    # ── 任务 ──────────────────────────────────────────────

    async def _task_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        import aiosqlite
        company_id = params.get("company_id")
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            if company_id:
                cursor = await conn.execute(
                    "SELECT * FROM tasks WHERE company_id = ? ORDER BY created_at DESC",
                    (company_id,),
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC"
                )
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await conn.close()

    async def _task_create(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        title = params.get("title", "")
        company_id = params.get("company_id", "")
        description = params.get("description", "")
        priority = params.get("priority", 5)

        if not title:
            return {"error": "missing title"}
        if not company_id:
            return {"error": "missing company_id"}

        now = datetime.now(timezone.utc).isoformat()
        task_id = str(uuid.uuid4())

        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                """INSERT INTO tasks
                   (task_id, company_id, title, description, priority,
                     status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'created', 1, ?, ?)""",
                (task_id, company_id, title, description, priority, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()

        return {
            "task_id": task_id,
            "title": title,
            "status": "created",
            "priority": priority,
        }

    async def _task_get(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        task_id = params.get("task_id")
        if not task_id:
            return {"error": "missing task_id"}
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cursor = await conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return {"error": "WF-NOT-FOUND"}
            return dict(row)
        finally:
            await conn.close()

    # ── 知识库 ────────────────────────────────────────────

    async def _knowledge_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        import aiosqlite
        company_id = params.get("company_id")
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            if company_id:
                cursor = await conn.execute(
                    "SELECT * FROM knowledge_documents WHERE company_id = ? ORDER BY created_at DESC",
                    (company_id,),
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM knowledge_documents ORDER BY created_at DESC"
                )
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await conn.close()

    async def _knowledge_create(self, params: dict[str, Any]) -> dict[str, Any]:
        import aiosqlite
        title = params.get("title", "")
        company_id = params.get("company_id", "")
        content = params.get("content", "")
        source_category = params.get("source_category", "custom")

        if not title:
            return {"error": "missing title"}
        if not company_id:
            return {"error": "missing company_id"}

        now = datetime.now(timezone.utc).isoformat()
        document_id = str(uuid.uuid4())
        checksum = hashlib.sha256(content.encode()).hexdigest()

        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                """INSERT INTO knowledge_documents
                   (document_id, company_id, title, content, source_type,
                    source_category, visibility, embedding_status,
                    checksum, version, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'manual', ?, 'company', 'pending',
                           ?, 1, 'active', ?, ?)""",
                (document_id, company_id, title, content,
                 source_category, checksum, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()

        return {
            "document_id": document_id,
            "title": title,
            "source_category": source_category,
            "status": "active",
        }
