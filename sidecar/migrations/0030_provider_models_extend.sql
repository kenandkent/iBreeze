-- 0030: 扩展 provider_models 至设计方案 §6.11 静态能力字段。
-- providers / provider_models 表在 0018 已建；此迁移由 schema_migrations 保证只应用一次。

ALTER TABLE provider_models ADD COLUMN source TEXT NOT NULL DEFAULT 'builtin_manifest';
ALTER TABLE provider_models ADD COLUMN manifest_version TEXT;
ALTER TABLE provider_models ADD COLUMN config_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE provider_models ADD COLUMN tier TEXT NOT NULL DEFAULT 'standard';
ALTER TABLE provider_models ADD COLUMN billing_mode TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE provider_models ADD COLUMN enforces_output_cap INTEGER NOT NULL DEFAULT 0;
ALTER TABLE provider_models ADD COLUMN context_window INTEGER NOT NULL DEFAULT 0;
ALTER TABLE provider_models ADD COLUMN latency_hint TEXT NOT NULL DEFAULT '';

-- 内置 manifest 按 (provider_id, model) WHERE owner_company_id IS NULL 幂等 upsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_models_builtin
    ON provider_models(provider_id, model)
    WHERE owner_company_id IS NULL;

-- 公司私有模型按 (owner_company_id, provider_id, model) 唯一
CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_models_company
    ON provider_models(owner_company_id, provider_id, model)
    WHERE owner_company_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_provider_models_provider ON provider_models(provider_id);
