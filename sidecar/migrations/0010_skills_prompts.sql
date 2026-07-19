CREATE TABLE IF NOT EXISTS prompt_assets (
    prompt_asset_id TEXT PRIMARY KEY,
    company_scope TEXT NOT NULL DEFAULT 'company' CHECK (company_scope IN ('global', 'company')),
    company_id TEXT,
    name TEXT NOT NULL,
    segments TEXT NOT NULL DEFAULT '{}',
    variables TEXT NOT NULL DEFAULT '[]',
    context_slots TEXT NOT NULL DEFAULT '[]',
    checksum TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'deprecated', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((company_scope = 'global' AND company_id IS NULL) OR (company_scope = 'company' AND company_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_prompt_assets_company ON prompt_assets(company_id);
CREATE INDEX IF NOT EXISTS idx_prompt_assets_status ON prompt_assets(status);

CREATE TABLE IF NOT EXISTS skills (
    skill_id TEXT PRIMARY KEY,
    company_scope TEXT NOT NULL DEFAULT 'company' CHECK (company_scope IN ('global', 'company')),
    company_id TEXT,
    name TEXT NOT NULL,
    prompt_asset_id TEXT NOT NULL,
    prompt_asset_version INTEGER NOT NULL,
    prompt_asset_checksum TEXT NOT NULL,
    tool_bindings TEXT NOT NULL DEFAULT '[]',
    knowledge_refs TEXT NOT NULL DEFAULT '[]',
    input_schema TEXT NOT NULL DEFAULT '{}',
    output_schema TEXT NOT NULL DEFAULT '{}',
    checksum TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'deprecated', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((company_scope = 'global' AND company_id IS NULL) OR (company_scope = 'company' AND company_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_skills_company ON skills(company_id);
CREATE INDEX IF NOT EXISTS idx_skills_prompt_asset ON skills(prompt_asset_id);
