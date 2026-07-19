-- 0003: 审计表（append-only）

-- ACL 审计日志
CREATE TABLE IF NOT EXISTS acl_audit_log (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    company_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    action TEXT NOT NULL,
    decision TEXT NOT NULL,
    matched_rule TEXT,
    scope_hash TEXT,
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_acl_audit_subject_time ON acl_audit_log(subject, timestamp);
CREATE INDEX IF NOT EXISTS idx_acl_audit_resource_time ON acl_audit_log(resource_type, resource_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_acl_audit_decision_time ON acl_audit_log(decision, timestamp);

-- 知识访问日志
CREATE TABLE IF NOT EXISTS knowledge_access_logs (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    operator TEXT,
    subject TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('search', 'list', 'get', 'citation', 'context_pack')),
    query_hash TEXT,
    scope_hash TEXT,
    result_knowledge_ids TEXT NOT NULL DEFAULT '[]',
    result_count INTEGER NOT NULL DEFAULT 0,
    decision TEXT NOT NULL,
    matched_rules TEXT NOT NULL DEFAULT '[]',
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_access_company_time ON knowledge_access_logs(company_id, timestamp);

-- 知识治理审计
CREATE TABLE IF NOT EXISTS knowledge_governance_audit (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_snapshot TEXT,
    after_snapshot TEXT,
    operator TEXT NOT NULL,
    reason TEXT,
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 组织变更审计
CREATE TABLE IF NOT EXISTS org_change_audit (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_snapshot TEXT,
    after_snapshot TEXT,
    operator TEXT NOT NULL,
    reason TEXT,
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_org_change_company_time ON org_change_audit(company_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_org_change_aggregate ON org_change_audit(company_id, aggregate_type, aggregate_id, timestamp);

-- 审计引用边
CREATE TABLE IF NOT EXISTS audit_record_refs (
    ref_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    audit_table TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    ref_type TEXT NOT NULL CHECK (ref_type IN ('evidence', 'citation', 'checkpoint', 'incident')),
    ref_id_value TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_refs_audit ON audit_record_refs(audit_table, audit_id);
