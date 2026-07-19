-- 0033: 公司级 Provider 可用性投影（probe 结果），设计方案 §6.11。
-- probe 只更新 (company_id, provider_id) 的 Availability，不改写全局静态能力。

CREATE TABLE IF NOT EXISTS provider_availability (
    company_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    available INTEGER NOT NULL DEFAULT 0,
    healthy INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    probed_at TEXT NOT NULL DEFAULT (datetime('now')),
    version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (company_id, provider_id)
);

CREATE INDEX IF NOT EXISTS idx_availability_company ON provider_availability(company_id);
