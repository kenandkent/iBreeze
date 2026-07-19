-- 0024: employees 表添加软删除字段

ALTER TABLE employees ADD COLUMN deleted_at TEXT;
ALTER TABLE employees ADD COLUMN deleted_by TEXT;
ALTER TABLE employees ADD COLUMN delete_reason TEXT;
