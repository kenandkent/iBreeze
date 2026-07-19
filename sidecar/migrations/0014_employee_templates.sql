CREATE TABLE IF NOT EXISTS employee_templates (
    template_id TEXT PRIMARY KEY,
    template_scope TEXT NOT NULL DEFAULT 'company' CHECK (template_scope IN ('global', 'company')),
    company_id TEXT,
    provider_type TEXT NOT NULL DEFAULT 'openai',
    provider_id TEXT NOT NULL DEFAULT 'openai',
    model TEXT NOT NULL DEFAULT 'gpt-4',
    capability_id TEXT NOT NULL,
    capability_version INTEGER NOT NULL,
    capability_snapshot TEXT NOT NULL DEFAULT '{}',
    default_role TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((template_scope = 'global' AND company_id IS NULL) OR (template_scope = 'company' AND company_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_emp_templates_company ON employee_templates(company_id);
