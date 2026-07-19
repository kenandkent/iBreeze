-- 0046: knowledge_citations 与 knowledge_ingestion_jobs（Phase 8 P8-T2）
--
-- citations：每个 chunk 恰有一条同公司、同 document/source 的引用；
--   仅存 locator/quote_hash 不复制原文。
-- ingestion_jobs：pending|running|retryable|succeeded|failed|cancelled 状态机，
--   锁定 policy id/version，以 source+policy+attempt 唯一、version CAS 收敛。

CREATE TABLE IF NOT EXISTS knowledge_citations (
    citation_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    locator TEXT NOT NULL DEFAULT '{}',
    quote_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_citations_chunk
    ON knowledge_citations(chunk_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_citations_doc
    ON knowledge_citations(document_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_citations_source
    ON knowledge_citations(source_record_id);

CREATE TABLE IF NOT EXISTS knowledge_ingestion_jobs (
    job_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'retryable', 'succeeded', 'failed', 'cancelled')),
    error_message TEXT,
    watermark_event_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, source_record_id, policy_id, policy_version, attempt)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_source
    ON knowledge_ingestion_jobs(source_record_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status
    ON knowledge_ingestion_jobs(company_id, status);
