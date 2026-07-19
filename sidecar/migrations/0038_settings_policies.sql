-- 0038: 设置模块策略表（workspace / notification）
-- 仅新增表，幂等；knowledge/security/embedding 策略表已在 0008 建立。

CREATE TABLE IF NOT EXISTS workspace_policies (
    policy_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_policies (
    policy_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_workspace_policies_company ON workspace_policies(company_id);
CREATE INDEX IF NOT EXISTS idx_notification_policies_company ON notification_policies(company_id);
