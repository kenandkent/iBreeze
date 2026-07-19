CREATE TABLE IF NOT EXISTS capabilities (
    capability_id TEXT PRIMARY KEY,
    company_scope TEXT NOT NULL DEFAULT 'company' CHECK (company_scope IN ('global', 'company')),
    company_id TEXT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    source_category TEXT NOT NULL DEFAULT 'custom',
    visibility TEXT NOT NULL DEFAULT 'company',
    cost_policy TEXT NOT NULL DEFAULT '{}',
    checksum TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'deprecated', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((company_scope = 'global' AND company_id IS NULL) OR (company_scope = 'company' AND company_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS skill_bindings (
    binding_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    capability_version INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    skill_id TEXT NOT NULL,
    skill_version INTEGER NOT NULL,
    skill_version_checksum TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_bindings_cap ON skill_bindings(capability_id, capability_version, ordinal);
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_bindings_skill ON skill_bindings(capability_id, capability_version, skill_id);
