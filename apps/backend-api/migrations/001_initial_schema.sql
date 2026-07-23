-- iBreeze Backend API PostgreSQL 完整 DDL 迁移
-- 对齐设计文档 G.3-G.7

-- ============================================================
-- G.3 用户 DDL
-- ============================================================

CREATE TABLE users (
    id UUID PRIMARY KEY,
    user_type VARCHAR(16) NOT NULL
        CHECK (user_type IN ('admin', 'app_user')),
    username VARCHAR(64),
    email VARCHAR(320),
    password_hash TEXT NOT NULL,
    display_name VARCHAR(320) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    CHECK (
        (user_type = 'admin' AND username IS NOT NULL AND email IS NULL)
        OR
        (user_type = 'app_user' AND email IS NOT NULL AND username IS NULL)
    ),
    CHECK (NOT protected OR user_type = 'admin')
);

CREATE UNIQUE INDEX uq_users_username_lower
    ON users (lower(username)) WHERE username IS NOT NULL;
CREATE UNIQUE INDEX uq_users_email_lower
    ON users (lower(email)) WHERE email IS NOT NULL;
CREATE INDEX ix_users_type_status ON users (user_type, status, created_at, id);

CREATE TABLE refresh_token_families (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revoke_reason VARCHAR(64),
    UNIQUE (user_id, device_id, id)
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY,
    family_id UUID NOT NULL REFERENCES refresh_token_families(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    replaced_by_id UUID REFERENCES refresh_tokens(id),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX ix_refresh_tokens_family_active
    ON refresh_tokens (family_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE api_idempotency (
    principal_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    method VARCHAR(8) NOT NULL,
    path TEXT NOT NULL,
    idempotency_key UUID NOT NULL,
    request_sha256 CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK(status IN ('processing','completed','failed')),
    response_status INTEGER,
    response_content_type VARCHAR(100),
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(principal_user_id, method, path, idempotency_key)
);
CREATE INDEX ix_api_idempotency_expiry ON api_idempotency(expires_at);

-- ============================================================
-- G.6 目录 DDL
-- ============================================================

CREATE TABLE agents (
    id UUID PRIMARY KEY,
    key VARCHAR(64) NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    display_name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, catalog_revision)
);

CREATE TABLE agent_versions (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES agents(id),
    min_version VARCHAR(64) NOT NULL,
    max_version_exclusive VARCHAR(64) NOT NULL,
    executable_names JSONB NOT NULL,
    supported_platforms JSONB NOT NULL,
    probe_argv JSONB NOT NULL,
    capability_tags JSONB NOT NULL,
    network_domains JSONB NOT NULL,
    adapter_contract_version INTEGER NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(agent_id, min_version, max_version_exclusive),
    CHECK(min_version <> max_version_exclusive)
);

CREATE TABLE models (
    id UUID PRIMARY KEY,
    provider_key VARCHAR(64) NOT NULL,
    model_key VARCHAR(200) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    context_window INTEGER NOT NULL CHECK (context_window > 0),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens > 0),
    tokenizer_key VARCHAR(100) NOT NULL,
    supports_tools BOOLEAN NOT NULL,
    supports_streaming BOOLEAN NOT NULL,
    supports_vision BOOLEAN NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(provider_key, model_key, catalog_revision)
);

CREATE TABLE agent_model_bindings (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES agents(id),
    model_id UUID NOT NULL REFERENCES models(id),
    min_agent_version VARCHAR(64) NOT NULL,
    max_agent_version_exclusive VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(agent_id, model_id, min_agent_version, max_agent_version_exclusive)
);

CREATE TABLE api_providers (
    id UUID PRIMARY KEY,
    key VARCHAR(64) NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    display_name VARCHAR(100) NOT NULL,
    protocol VARCHAR(32) NOT NULL
        CHECK (protocol IN ('openai_responses','anthropic_messages','openai_chat_completions')),
    base_url TEXT NOT NULL,
    auth_scheme VARCHAR(32) NOT NULL CHECK (auth_scheme IN ('bearer','x-api-key')),
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, catalog_revision)
);

CREATE TABLE provider_model_bindings (
    id UUID PRIMARY KEY,
    provider_id UUID NOT NULL REFERENCES api_providers(id),
    model_id UUID NOT NULL REFERENCES models(id),
    provider_model_name VARCHAR(200) NOT NULL,
    request_defaults JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(provider_id, model_id)
);

CREATE TABLE skills (
    id UUID PRIMARY KEY,
    key VARCHAR(100) NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    display_name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, catalog_revision)
);

CREATE TABLE skill_versions (
    id UUID PRIMARY KEY,
    skill_id UUID NOT NULL REFERENCES skills(id),
    version VARCHAR(64) NOT NULL,
    manifest_json JSONB NOT NULL,
    object_key TEXT NOT NULL UNIQUE,
    object_size BIGINT NOT NULL CHECK (object_size BETWEEN 1 AND 52428800),
    object_sha256 CHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signing_key_id VARCHAR(100) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(skill_id, version)
);

CREATE TABLE compatibility_rules (
    id UUID PRIMARY KEY,
    subject_type VARCHAR(32) NOT NULL
        CHECK (subject_type IN ('agent','model','skill','client')),
    subject_id UUID NOT NULL,
    subject_version_range VARCHAR(200) NOT NULL,
    dependency_type VARCHAR(32) NOT NULL
        CHECK (dependency_type IN ('agent','model','skill','platform','client')),
    dependency_key VARCHAR(200) NOT NULL,
    dependency_version_range VARCHAR(200) NOT NULL,
    decision VARCHAR(8) NOT NULL CHECK (decision IN ('allow','deny')),
    reason_code VARCHAR(100) NOT NULL,
    priority INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX ix_compatibility_subject
    ON compatibility_rules(subject_type, subject_id, priority DESC);

-- ============================================================
-- G.7 发布 DDL
-- ============================================================

CREATE TABLE catalog_releases (
    id UUID PRIMARY KEY,
    release_sequence BIGINT NOT NULL UNIQUE CHECK (release_sequence > 0),
    minimum_client_version VARCHAR(64) NOT NULL,
    manifest_object_key TEXT NOT NULL UNIQUE,
    manifest_sha256 CHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signing_key_id VARCHAR(100) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('publishing','published','failed')),
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE TABLE catalog_release_items (
    release_id UUID NOT NULL REFERENCES catalog_releases(id),
    resource_type VARCHAR(32) NOT NULL CHECK(resource_type IN (
        'agent_revision','agent_version','model','provider',
        'skill_revision','skill_version','compatibility_rule'
    )),
    resource_id UUID NOT NULL,
    resource_version_id UUID NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    PRIMARY KEY(release_id, resource_type, resource_id, resource_version_id)
);

CREATE TABLE emergency_disable_releases (
    id UUID PRIMARY KEY,
    sequence BIGINT NOT NULL UNIQUE,
    payload_json JSONB NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signing_key_id VARCHAR(100) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE admin_audit_logs (
    id UUID PRIMARY KEY,
    actor_user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID,
    request_id UUID NOT NULL,
    outcome VARCHAR(16) NOT NULL CHECK (outcome IN ('success','denied','failed')),
    before_json JSONB,
    after_json JSONB,
    error_code VARCHAR(100),
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_admin_audit_created ON admin_audit_logs(created_at DESC, id);
CREATE INDEX ix_admin_audit_resource ON admin_audit_logs(resource_type, resource_id, created_at DESC);

-- ============================================================
-- G.7 发布不可变性触发器
-- ============================================================

CREATE OR REPLACE FUNCTION protect_catalog_resource_revision()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' THEN
            RAISE EXCEPTION 'catalog revision must be inserted as draft'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog revision is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog revision is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'UPDATE'
       AND NEW.status = 'published'
       AND OLD.status <> 'validated' THEN
        RAISE EXCEPTION 'only validated revision can be published'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agents_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON agents
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER models_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON models
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER providers_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON api_providers
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER skills_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON skills
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER compatibility_rules_guard
BEFORE INSERT OR UPDATE OR DELETE ON compatibility_rules
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();

CREATE OR REPLACE FUNCTION protect_catalog_version()
RETURNS trigger AS $$
DECLARE
    parent_status VARCHAR(16);
    parent_id UUID;
BEGIN
    IF TG_TABLE_NAME = 'agent_versions' THEN
        IF TG_OP = 'DELETE' THEN parent_id := OLD.agent_id; ELSE parent_id := NEW.agent_id; END IF;
        SELECT status INTO parent_status FROM agents
        WHERE id = parent_id FOR UPDATE;
    ELSIF TG_TABLE_NAME = 'skill_versions' THEN
        IF TG_OP = 'DELETE' THEN parent_id := OLD.skill_id; ELSE parent_id := NEW.skill_id; END IF;
        SELECT status INTO parent_status FROM skills
        WHERE id = parent_id FOR UPDATE;
    END IF;
    IF parent_status = 'published' THEN
        RAISE EXCEPTION 'published parent revision children are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'catalog version must be inserted unpublished'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.published_at IS NOT NULL THEN
        RAISE EXCEPTION 'published catalog version is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NEW.published_at IS NOT NULL AND OLD.published_at IS NULL THEN
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_versions_guard
BEFORE INSERT OR UPDATE OR DELETE ON agent_versions
FOR EACH ROW EXECUTE FUNCTION protect_catalog_version();
CREATE TRIGGER skill_versions_guard
BEFORE INSERT OR UPDATE OR DELETE ON skill_versions
FOR EACH ROW EXECUTE FUNCTION protect_catalog_version();

CREATE OR REPLACE FUNCTION reject_catalog_release_item_mutation()
RETURNS trigger AS $$
DECLARE
    parent_status VARCHAR(16);
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT status INTO parent_status
        FROM catalog_releases
        WHERE id = NEW.release_id
        FOR UPDATE;
        IF parent_status IS DISTINCT FROM 'publishing' THEN
            RAISE EXCEPTION 'items can only be inserted into publishing release'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'catalog release item is immutable'
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalog_release_items_immutable
BEFORE INSERT OR UPDATE OR DELETE ON catalog_release_items
FOR EACH ROW EXECUTE FUNCTION reject_catalog_release_item_mutation();

CREATE OR REPLACE FUNCTION reject_append_only_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only row is immutable'
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER emergency_disable_releases_immutable
BEFORE UPDATE OR DELETE ON emergency_disable_releases
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER admin_audit_logs_immutable
BEFORE UPDATE OR DELETE ON admin_audit_logs
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE OR REPLACE FUNCTION protect_catalog_release()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'publishing' THEN
            RAISE EXCEPTION 'catalog release must be inserted as publishing'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog release is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog release is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalog_releases_guard
BEFORE INSERT OR UPDATE OR DELETE ON catalog_releases
FOR EACH ROW EXECUTE FUNCTION protect_catalog_release();
