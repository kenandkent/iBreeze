-- 0045: knowledge_sources 派生链来源索引（Phase 8 P8-T1）
--
-- 不是第二套事件正文，而是派生链来源索引。一个 source 可对应 0..N 个 document。
-- UNIQUE(company_id, source_type, source_id)；事件来源保存 source_event_id，
-- file/manual 保存受 path broker 校验的 original_ref。

CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_record_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_event_id TEXT,
    original_ref TEXT,
    derived_document_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, source_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_sources_company ON knowledge_sources(company_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_event
    ON knowledge_sources(source_event_id);
