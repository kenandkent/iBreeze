-- 0041: conversation_events 消息/工具事件事实表（Phase 7 投影源）
--
-- 唯一约束 (thread_id, sequence)。每条事件带 schema_version、canonical checksum、
-- provider 归一化后的 payload，供 transcript.jsonl 幂等重建。

CREATE TABLE IF NOT EXISTS conversation_events (
    event_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES session_threads(thread_id),
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'acos:conversation-event:v1',
    event_type TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    tool_name TEXT,
    tool_request_hash TEXT,
    artifact_ref TEXT,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    provider_native_event_id TEXT,
    canonical_checksum TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (thread_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_conversation_events_thread
    ON conversation_events(thread_id, sequence);
CREATE INDEX IF NOT EXISTS idx_conversation_events_company
    ON conversation_events(company_id, employee_id);
