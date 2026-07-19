-- 0031: 版本化价格目录（append-only），设计方案 §6.11。
-- 金额一律 int64 micros（每百万 token 单价），禁止 binary float。
-- verified_at 由服务端注入，历史版本禁止覆盖。

CREATE TABLE IF NOT EXISTS provider_model_prices (
    pricing_version_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_per_1m_micros INTEGER NOT NULL,
    output_per_1m_micros INTEGER NOT NULL,
    cache_per_1m_micros INTEGER,
    tool_call_flat_micros INTEGER,
    currency TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    source TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (input_per_1m_micros >= 0),
    CHECK (output_per_1m_micros >= 0),
    CHECK (cache_per_1m_micros IS NULL OR cache_per_1m_micros >= 0),
    CHECK (tool_call_flat_micros IS NULL OR tool_call_flat_micros >= 0)
);

-- 同一 (company,provider,model,currency,effective_at) 只允许一个价格版本，历史不覆盖
CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_version_key
    ON provider_model_prices(company_id, provider_id, model, currency, effective_at);

CREATE INDEX IF NOT EXISTS idx_prices_resolve
    ON provider_model_prices(company_id, provider_id, model, currency, effective_at DESC);
