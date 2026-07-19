-- employee_reporting_closure: 汇报链闭包表
-- 用于高效查询某职员的所有下属（包含间接下属）
-- 由 setManager 同事务维护：增删移动子树时更新闭包行

CREATE TABLE IF NOT EXISTS employee_reporting_closure (
    company_id TEXT NOT NULL,
    ancestor_employee_id TEXT NOT NULL,
    descendant_employee_id TEXT NOT NULL,
    depth INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (company_id, ancestor_employee_id, descendant_employee_id)
);
CREATE INDEX IF NOT EXISTS idx_emp_reporting_closure_descendant
    ON employee_reporting_closure(company_id, descendant_employee_id);
CREATE INDEX IF NOT EXISTS idx_emp_reporting_closure_ancestor
    ON employee_reporting_closure(company_id, ancestor_employee_id);