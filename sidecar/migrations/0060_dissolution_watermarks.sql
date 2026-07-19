-- 0060: 公司解散 watermark 表（P2-T1 协调器）
-- 跟踪 6 个消费者（organization, task, session, knowledge, provider, backend）
-- 完成公司解散的状态，全部 completed 后才允许转为 dissolved。

CREATE TABLE IF NOT EXISTS dissolution_watermarks (
    company_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    completed_at TEXT,
    error_detail TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (company_id, consumer_name)
);

CREATE INDEX IF NOT EXISTS idx_dissolution_watermarks_company
    ON dissolution_watermarks(company_id);
