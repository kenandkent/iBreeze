-- 0049: knowledge_documents / knowledge_chunks 补字段（Phase 8 P8-T2/T3/T4）
--
-- 文档按可见性等级分支下推：company / department / task / employee。
-- document.source_category 从 knowledge_sources 不可变物化，供 FTS/LanceDB 预过滤。
-- chunks 与 LanceDB 都存 generation_id，按 (chunk_id, generation_id) 幂等。

-- knowledge_documents 补字段
ALTER TABLE knowledge_documents ADD COLUMN source_record_id TEXT;
ALTER TABLE knowledge_documents ADD COLUMN department_id TEXT;
ALTER TABLE knowledge_documents ADD COLUMN task_id TEXT;
ALTER TABLE knowledge_documents ADD COLUMN employee_id TEXT;
ALTER TABLE knowledge_documents ADD COLUMN policy_version INTEGER;
ALTER TABLE knowledge_documents ADD COLUMN generation_id TEXT;
ALTER TABLE knowledge_documents ADD COLUMN governance_confirmed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE knowledge_documents ADD COLUMN deleted_at TEXT;

CREATE INDEX IF NOT EXISTS idx_knowledge_docs_visibility
    ON knowledge_documents(company_id, visibility);
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_source
    ON knowledge_documents(source_record_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_dept
    ON knowledge_documents(company_id, department_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_task
    ON knowledge_documents(company_id, task_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_docs_employee
    ON knowledge_documents(company_id, employee_id);

-- knowledge_chunks 补字段
ALTER TABLE knowledge_chunks ADD COLUMN generation_id TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN source_record_id TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN visibility TEXT NOT NULL DEFAULT 'company';
ALTER TABLE knowledge_chunks ADD COLUMN department_id TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN task_id TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN employee_id TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN vector_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE knowledge_chunks ADD COLUMN deleted_at TEXT;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_gen
    ON knowledge_chunks(generation_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_visibility
    ON knowledge_chunks(company_id, visibility);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source
    ON knowledge_chunks(source_record_id);
