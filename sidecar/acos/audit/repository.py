"""审计记录仓库 - 只提供 insert 接口（append-only）。"""

from __future__ import annotations

import json

import aiosqlite

from acos.audit.models import (
    ACLAuditLog,
    AuditRecordRef,
    KnowledgeAccessLog,
    KnowledgeGovernanceAudit,
    OrgChangeAudit,
)


class AuditRepository:
    """审计记录仓库 - 只提供 insert 接口。"""

    async def write_acl_audit(self, conn: aiosqlite.Connection, record: ACLAuditLog) -> str:
        """写入 ACL 审计日志，返回 id。"""
        await conn.execute(
            """INSERT INTO acl_audit_log
               (id, subject, company_id, resource_type, resource_id,
                action, decision, matched_rule, scope_hash, trace_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.subject,
                record.company_id,
                record.resource_type,
                record.resource_id,
                record.action,
                record.decision,
                record.matched_rule,
                record.scope_hash,
                record.trace_id,
                record.timestamp,
            ),
        )
        await conn.commit()
        return record.id

    async def write_knowledge_access(
        self, conn: aiosqlite.Connection, record: KnowledgeAccessLog
    ) -> str:
        """写入知识访问日志，返回 id。"""
        await conn.execute(
            """INSERT INTO knowledge_access_logs
               (id, company_id, operator, subject, action, query_hash, scope_hash,
                result_knowledge_ids, result_count, decision, matched_rules,
                trace_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.company_id,
                record.operator,
                record.subject,
                record.action,
                record.query_hash,
                record.scope_hash,
                json.dumps(record.result_knowledge_ids, ensure_ascii=False),
                record.result_count,
                record.decision,
                json.dumps(record.matched_rules, ensure_ascii=False),
                record.trace_id,
                record.timestamp,
            ),
        )
        await conn.commit()
        return record.id

    async def write_knowledge_governance_audit(
        self, conn: aiosqlite.Connection, record: KnowledgeGovernanceAudit
    ) -> str:
        """写入知识治理审计，返回 id。"""
        await conn.execute(
            """INSERT INTO knowledge_governance_audit
               (id, company_id, resource_type, resource_id, action,
                before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.company_id,
                record.resource_type,
                record.resource_id,
                record.action,
                record.before_snapshot,
                record.after_snapshot,
                record.operator,
                record.reason,
                record.trace_id,
                record.timestamp,
            ),
        )
        await conn.commit()
        return record.id

    async def write_org_change_audit(
        self, conn: aiosqlite.Connection, record: OrgChangeAudit
    ) -> str:
        """写入组织变更审计，返回 id。"""
        await conn.execute(
            """INSERT INTO org_change_audit
               (id, company_id, aggregate_type, aggregate_id, action,
                before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.company_id,
                record.aggregate_type,
                record.aggregate_id,
                record.action,
                record.before_snapshot,
                record.after_snapshot,
                record.operator,
                record.reason,
                record.trace_id,
                record.timestamp,
            ),
        )
        await conn.commit()
        return record.id

    async def write_audit_ref(self, conn: aiosqlite.Connection, record: AuditRecordRef) -> str:
        """写入审计引用边，返回 ref_id。"""
        await conn.execute(
            """INSERT INTO audit_record_refs
               (ref_id, company_id, audit_table, audit_id, ref_type, ref_id_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.ref_id,
                record.company_id,
                record.audit_table,
                record.audit_id,
                record.ref_type,
                record.ref_id_value,
                record.created_at,
            ),
        )
        await conn.commit()
        return record.ref_id
