-- 0025: 能力资产版本表（Skill / PromptAsset / Capability 版本状态机）
-- 主表保留 inline status/version 作为"当前发布指针"，状态机在 *_versions 表上操作。

CREATE TABLE IF NOT EXISTS skill_versions (
    skill_version_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    prompt_asset_id TEXT NOT NULL,
    prompt_asset_version INTEGER NOT NULL,
    prompt_asset_checksum TEXT NOT NULL,
    tool_bindings TEXT NOT NULL DEFAULT '[]',
    knowledge_refs TEXT NOT NULL DEFAULT '[]',
    input_schema TEXT NOT NULL DEFAULT '{}',
    output_schema TEXT NOT NULL DEFAULT '{}',
    checksum TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'deprecated', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (skill_id, version)
);

CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_versions_status ON skill_versions(status);

CREATE TABLE IF NOT EXISTS prompt_asset_versions (
    prompt_asset_version_id TEXT PRIMARY KEY,
    prompt_asset_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    segments TEXT NOT NULL DEFAULT '{}',
    variables TEXT NOT NULL DEFAULT '[]',
    context_slots TEXT NOT NULL DEFAULT '[]',
    checksum TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'deprecated', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (prompt_asset_id, version)
);

CREATE INDEX IF NOT EXISTS idx_prompt_asset_versions_asset ON prompt_asset_versions(prompt_asset_id);
CREATE INDEX IF NOT EXISTS idx_prompt_asset_versions_status ON prompt_asset_versions(status);

CREATE TABLE IF NOT EXISTS capability_versions (
    capability_version_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    cost_policy TEXT NOT NULL DEFAULT '{}',
    skill_bindings TEXT NOT NULL DEFAULT '[]',
    stability_level INTEGER,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'deprecated', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (capability_id, version)
);

CREATE INDEX IF NOT EXISTS idx_capability_versions_cap ON capability_versions(capability_id);
CREATE INDEX IF NOT EXISTS idx_capability_versions_status ON capability_versions(status);
