"""审计记录 dataclass（只读，无 update/delete）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ACLAuditLog:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject: str = ""
    company_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    action: str = ""
    decision: str = ""
    matched_rule: str = ""
    scope_hash: str = ""
    trace_id: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class KnowledgeAccessLog:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    operator: str = ""
    subject: str = ""
    action: str = ""
    query_hash: str = ""
    scope_hash: str = ""
    result_knowledge_ids: list[str] = field(default_factory=list)
    result_count: int = 0
    decision: str = ""
    matched_rules: list[dict] = field(default_factory=list)
    trace_id: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class KnowledgeGovernanceAudit:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    action: str = ""
    before_snapshot: str = ""
    after_snapshot: str = ""
    operator: str = ""
    reason: str = ""
    trace_id: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class OrgChangeAudit:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    aggregate_type: str = ""
    aggregate_id: str = ""
    action: str = ""
    before_snapshot: str = ""
    after_snapshot: str = ""
    operator: str = ""
    reason: str = ""
    trace_id: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class AuditRecordRef:
    ref_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    audit_table: str = ""
    audit_id: str = ""
    ref_type: str = ""
    ref_id_value: str = ""
    created_at: str = ""
