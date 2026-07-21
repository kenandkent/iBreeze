import sqlite3

import pytest


EXPECTED_TABLES = {
    "access_grants",
    "admin_sessions",
    "admin_users",
    "approval_types",
    "audit_log",
    "backends",
    "budget_policies",
    "capabilities",
    "capability_versions",
    "companies",
    "company_backend_defaults",
    "departments",
    "employee_templates",
    "employees",
    "knowledge_documents",
    "knowledge_policies",
    "knowledge_sources",
    "notification_policies",
    "prompt_asset_versions",
    "prompt_assets",
    "provider_credentials",
    "provider_models",
    "provider_pricing_versions",
    "provider_tier_mappings",
    "providers",
    "security_policies",
    "skill_bindings",
    "skill_versions",
    "skills",
    "workspace_policies",
}


def test_all_tables_exist():
    conn = sqlite3.connect("/tmp/ibreeze_admin.db")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Missing tables: {missing}"


def test_alembic_version_exists():
    conn = sqlite3.connect("/tmp/ibreeze_admin.db")
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    conn.close()
    assert row is not None, "alembic_version table is empty"
