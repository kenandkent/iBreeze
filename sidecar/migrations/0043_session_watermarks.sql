-- 0043: 会话 watermark（Phase 7-T5 公司解散/职员归档协调）
--
-- 消费 CompanyDissolutionStarted / EmployeeArchived 后，Sidecar 在确认全部会话线程
-- 已归档、对应 Backend lease 已释放时，持久化 Session watermark，供 P2-T1 协调器
-- 与 Backend watermark 共同决定是否允许 CompanyDissolved。

CREATE TABLE IF NOT EXISTS session_watermarks (
    watermark_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('company', 'employee')),
    target_id TEXT NOT NULL,
    trigger_event TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'consumed' CHECK (status IN ('consumed', 'pending')),
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_session_watermarks_company
    ON session_watermarks(company_id, scope, target_id);
