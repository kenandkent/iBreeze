-- 0042: 会话调岗 Handoff 对账日志（Phase 7-T4）
--
-- 记录 EmployeeTransferred（全流程恰好一次写入）、EmployeeTransferNeedsRepair、
-- 以及 drain port 的 suspend/archive 操作幂等 ACK。reconciler 据此判定 completed/needs_repair。

CREATE TABLE IF NOT EXISTS session_transfer_journal (
    journal_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('EmployeeTransferred','EmployeeTransferNeedsRepair',
                               'EmployeeSuspended','EmployeeArchived','EmployeeResumed')),
    drain_id TEXT,
    old_thread_id TEXT,
    new_thread_id TEXT,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_session_transfer_journal_transferred
    ON session_transfer_journal(employee_id, event_type)
    WHERE event_type = 'EmployeeTransferred';

CREATE INDEX IF NOT EXISTS idx_session_transfer_journal_company
    ON session_transfer_journal(company_id, event_type);
