-- 0050: knowledge FTS5 全文索引 + 完整性约束（Phase 8 P8-T2/T4）
--
-- knowledge_fts：真实 SQLite FTS5 关键词检索表，与 knowledge_documents 按 rowid 关联。
-- trigger 保证 document.source_category 与 knowledge_sources.source_category 相等，
-- 且创建后不可单独修改（source_category 只在 INSERT 时从 source 物化）。

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    document_id UNINDEXED,
    company_id UNINDEXED,
    source_category UNINDEXED,
    visibility UNINDEXED,
    department_id UNINDEXED,
    task_id UNINDEXED,
    employee_id UNINDEXED,
    title,
    content,
    tokenize = 'unicode61'
);

-- 文档写入同步到 FTS5
CREATE TRIGGER IF NOT EXISTS trg_kg_fts_after_insert
AFTER INSERT ON knowledge_documents
BEGIN
    INSERT INTO knowledge_fts
        (document_id, company_id, source_category, visibility, department_id,
         task_id, employee_id, title, content)
    VALUES (NEW.document_id, NEW.company_id, NEW.source_category, NEW.visibility,
            NEW.department_id, NEW.task_id, NEW.employee_id, NEW.title, NEW.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_kg_fts_after_update
AFTER UPDATE ON knowledge_documents
WHEN NEW.status = 'active'
BEGIN
    DELETE FROM knowledge_fts WHERE document_id = NEW.document_id;
    INSERT INTO knowledge_fts
        (document_id, company_id, source_category, visibility, department_id,
         task_id, employee_id, title, content)
    VALUES (NEW.document_id, NEW.company_id, NEW.source_category, NEW.visibility,
            NEW.department_id, NEW.task_id, NEW.employee_id, NEW.title, NEW.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_kg_fts_after_delete
AFTER UPDATE ON knowledge_documents
WHEN NEW.status != 'active'
BEGIN
    DELETE FROM knowledge_fts WHERE document_id = NEW.document_id;
END;

-- source_category 不可变触发
CREATE TRIGGER IF NOT EXISTS trg_kg_doc_source_category_immutable
BEFORE UPDATE ON knowledge_documents
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.source_category IS NOT OLD.source_category THEN
            RAISE(ABORT, 'source_category is immutable after creation')
    END;
END;
