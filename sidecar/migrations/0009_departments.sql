-- 0009: 部门树 + 闭包表

CREATE TABLE IF NOT EXISTS departments (
    department_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    parent_department_id TEXT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    responsibilities TEXT DEFAULT '[]',
    leader_employee_id TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'frozen', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    version INTEGER NOT NULL DEFAULT 1,
    deleted_at TEXT,
    deleted_by TEXT,
    delete_reason TEXT
);

CREATE TABLE IF NOT EXISTS department_closure (
    company_id TEXT NOT NULL,
    ancestor_department_id TEXT NOT NULL,
    descendant_department_id TEXT NOT NULL,
    depth INTEGER NOT NULL,
    PRIMARY KEY (company_id, ancestor_department_id, descendant_department_id)
);

CREATE INDEX IF NOT EXISTS idx_departments_company ON departments(company_id);
CREATE INDEX IF NOT EXISTS idx_dept_closure_descendant ON department_closure(company_id, descendant_department_id);
