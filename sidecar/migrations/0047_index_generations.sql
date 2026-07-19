-- 0047: index_generations（Phase 8 P8-T3）
--
-- 按设计方案 §9.5：generation_id UUID PK / company / model / version / dimension /
-- generation / status；company+generation 唯一且每公司最多一条 active。

CREATE TABLE IF NOT EXISTS index_generations (
    generation_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    model TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    dimension INTEGER NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'building'
        CHECK (status IN ('building', 'active', 'retiring', 'retired', 'failed')),
    pointer_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, generation)
);

CREATE INDEX IF NOT EXISTS idx_index_generations_company
    ON index_generations(company_id, status);
