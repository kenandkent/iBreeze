-- 0050: knowledge 完整性约束（Phase 8 P8-T2）
--
-- trigger 保证 document.source_category 与 knowledge_sources.source_category 相等，
-- 且创建后不可单独修改（source_category 只在 INSERT 时从 source 物化）。

CREATE TRIGGER IF NOT EXISTS trg_kg_doc_source_category_immutable
BEFORE UPDATE ON knowledge_documents
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.source_category IS NOT OLD.source_category THEN
            RAISE(ABORT, 'source_category is immutable after creation')
    END;
END;

-- 通知投递辅助：knowledge notification outbox 由应用层驱动，这里仅建投递标记视图所需的
-- 列已含于 jobs 表；本迁移保留用于将来扩展，无额外 DDL 以免重复。
