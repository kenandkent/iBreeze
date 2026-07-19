-- 0048: knowledge_governance_audit 扩展（Phase 8 P8-T4a）
--
-- 该表已由 0003_audit_tables.sql 建立（列：id/company_id/resource_type/resource_id/
-- action/before_snapshot/after_snapshot/operator/reason/trace_id/timestamp）。
-- 本迁移幂等补充 kg.* 治理命令所需列，并建索引。

ALTER TABLE knowledge_governance_audit ADD COLUMN operator_type TEXT NOT NULL DEFAULT 'local_owner';
ALTER TABLE knowledge_governance_audit ADD COLUMN target_type TEXT;
ALTER TABLE knowledge_governance_audit ADD COLUMN target_id TEXT;
ALTER TABLE knowledge_governance_audit ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_kg_gov_audit_company
    ON knowledge_governance_audit(company_id, target_id);
CREATE INDEX IF NOT EXISTS idx_kg_gov_audit_action
    ON knowledge_governance_audit(company_id, action);
