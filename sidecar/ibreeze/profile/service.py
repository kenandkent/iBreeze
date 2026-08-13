"""Employee base profile management service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ibreeze.routing.policy import validate_routing_policy


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def create_draft(
    db: Any,
    company_id: str,
    *,
    employee_id: str,
    agent_cli: str,
    api_model: str,
    base_profile: dict[str, object],
    credential_ref: str = "",
    provider_release_id: str = "",
    model_binding_id: str = "",
    provider_protocol: str = "",
    routing_policy: dict[str, object] | None = None,
) -> dict[str, object]:
    """Create a new profile draft version."""
    profile_id = _id()
    version_id = _id()
    now = _now()

    employee = await _one(
        await db.execute(
            "SELECT id FROM employees WHERE id=? AND company_id=?",
            (employee_id, company_id),
        )
    )
    if employee is None:
        raise ValueError("EMPLOYEE_NOT_FOUND")

    existing = await _one(
        await db.execute(
            """SELECT id FROM employee_base_profile_versions
               WHERE profile_id=? AND status='draft'""",
            (profile_id,),
        )
    )
    if existing is not None:
        raise ValueError("DRAFT_ALREADY_EXISTS")

    normalized_name = str(base_profile.get("name", "")).strip().lower()

    runtime_binding = {
        "agent_cli": agent_cli,
        "api_model": api_model,
        "credential_ref": credential_ref,
        "provider_release_id": provider_release_id,
        "model_binding_id": model_binding_id,
        "provider_protocol": provider_protocol,
    }
    profile_type = "agent_cli" if agent_cli else "api_model"
    if profile_type == "api_model":
        raw_policy = routing_policy or base_profile.get("routing_policy")
        validated = validate_routing_policy(
            raw_policy if isinstance(raw_policy, dict) else None,
            profile_type=profile_type,
        )
        policy_json = validated.canonical_json
    elif routing_policy:
        raise ValueError("ROUTING_POLICY_FORBIDDEN")
    else:
        policy_json = "{}"
    await db.execute(
        """INSERT INTO employee_base_profiles
           (id, company_id, name, normalized_name, description, status,
            created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            profile_id,
            company_id,
            base_profile.get("name", ""),
            normalized_name,
            base_profile.get("description", ""),
            "active",
            now,
            now,
            1,
        ),
    )

    await db.execute(
        """INSERT INTO employee_base_profile_versions
           (id, profile_id, version_number, name, description, profile_type,
            runtime_binding_json, routing_policy_json, system_prompt, capability_tags_json,
            tool_policy_json, timeout_seconds, max_retries,
            workspace_policy, catalog_release_id, content_sha256,
            status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            version_id,
            profile_id,
            1,
            base_profile.get("name", ""),
            base_profile.get("description", ""),
            profile_type,
            json.dumps(runtime_binding, sort_keys=True),
            policy_json,
            base_profile.get("system_prompt", ""),
            json.dumps(base_profile.get("capability_tags", [])),
            json.dumps(base_profile.get("tool_policy", {})),
            base_profile.get("timeout_seconds", 3600),
            base_profile.get("max_retries", 3),
            "workspace_rw_external_ro",
            base_profile.get("catalog_release_id", ""),
            base_profile.get("content_sha256", ""),
            "draft",
            now,
        ),
    )

    await db.execute(
        """UPDATE employee_base_profiles
           SET current_version_id=?, updated_at=?
           WHERE id=?""",
        (version_id, now, profile_id),
    )

    return {
        "profile_id": profile_id,
        "version_id": version_id,
        "status": "draft",
    }


async def update_draft(
    db: Any,
    company_id: str,
    draft_id: str,
    *,
    agent_cli: str,
    api_model: str,
    credential_ref: str | None = None,
    provider_release_id: str | None = None,
    model_binding_id: str | None = None,
    provider_protocol: str | None = None,
    routing_policy: dict[str, object] | None = None,
) -> dict[str, object]:
    """Update an existing draft."""
    now = _now()

    draft = await _one(
        await db.execute(
            """SELECT v.* FROM employee_base_profile_versions v
               JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE v.id=? AND v.status='draft' AND p.company_id=?""",
            (draft_id, company_id),
        )
    )
    if draft is None:
        raise ValueError("DRAFT_NOT_FOUND")

    profile_type = str(draft["profile_type"])
    policy_json: str | None = None
    if routing_policy is not None:
        if profile_type == "agent_cli":
            raise ValueError("ROUTING_POLICY_FORBIDDEN")
        policy_json = validate_routing_policy(
            routing_policy,
            profile_type=profile_type,
        ).canonical_json

    try:
        runtime_binding = json.loads(draft["runtime_binding_json"] or "{}")
    except (TypeError, ValueError):
        runtime_binding = {}
    updates = {
        "agent_cli": agent_cli,
        "api_model": api_model,
        "credential_ref": credential_ref,
        "provider_release_id": provider_release_id,
        "model_binding_id": model_binding_id,
        "provider_protocol": provider_protocol,
    }
    for key, value in updates.items():
        if value is not None and value != "":
            runtime_binding[key] = value
    runtime_binding = {str(key): value for key, value in runtime_binding.items()}
    if policy_json is None:
        update_sql = """UPDATE employee_base_profile_versions
           SET runtime_binding_json=?
           WHERE id=? AND status='draft'
             AND profile_id IN (SELECT id FROM employee_base_profiles WHERE company_id=?)"""
        update_args: tuple[Any, ...] = (json.dumps(runtime_binding, sort_keys=True), draft_id, company_id)
    else:
        update_sql = """UPDATE employee_base_profile_versions
           SET runtime_binding_json=?, routing_policy_json=?
           WHERE id=? AND status='draft'
             AND profile_id IN (SELECT id FROM employee_base_profiles WHERE company_id=?)"""
        update_args = (json.dumps(runtime_binding, sort_keys=True), policy_json, draft_id, company_id)
    await db.execute(update_sql, update_args)

    return {
        "version_id": draft_id,
        "status": "draft",
        "updated_at": now,
    }


async def get_profile(
    db: Any,
    company_id: str,
    profile_id: str,
) -> dict[str, object] | None:
    """Return profile with versions."""
    profile = await _one(
        await db.execute(
            "SELECT * FROM employee_base_profiles WHERE id=? AND company_id=?",
            (profile_id, company_id),
        )
    )
    if profile is None:
        return None

    cursor = await db.execute(
        """SELECT * FROM employee_base_profile_versions
           WHERE profile_id=?
           ORDER BY version_number DESC""",
        (profile_id,),
    )
    versions = [dict(row) for row in await cursor.fetchall()]

    return {**dict(profile), "versions": versions}


async def list_profiles(
    db: Any,
    company_id: str,
    *,
    employee_id: str | None = None,
) -> list[dict[str, object]]:
    """List all profiles, optional filter by employee (via employees table join)."""
    if employee_id is not None:
        cursor = await db.execute(
            """SELECT p.* FROM employee_base_profiles p
               JOIN employees e ON e.base_profile_version_id = p.current_version_id
               WHERE p.company_id=? AND e.id=? AND e.company_id=?
               ORDER BY p.created_at DESC, p.id DESC""",
            (company_id, employee_id, company_id),
        )
    else:
        cursor = await db.execute(
            """SELECT * FROM employee_base_profiles
               WHERE company_id=?
               ORDER BY created_at DESC, id DESC""",
            (company_id,),
        )
    return [dict(row) for row in await cursor.fetchall()]


async def bind_skill(
    db: Any,
    company_id: str,
    profile_id: str,
    *,
    skill_id: str,
    skill_version: str,
    package_sha256: str = "",
) -> dict[str, object]:
    """Bind a skill to profile."""
    import hashlib as _hashlib

    _now()

    draft = await _one(
        await db.execute(
            """SELECT v.id FROM employee_base_profile_versions v
               JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE v.profile_id=? AND v.status='draft' AND p.company_id=?""",
            (profile_id, company_id),
        )
    )
    if draft is None:
        raise ValueError("DRAFT_NOT_FOUND")

    existing = await _one(
        await db.execute(
            """SELECT 1 FROM profile_skill_bindings
               WHERE profile_version_id=? AND skill_id=?""",
            (draft["id"], skill_id),
        )
    )
    if existing is not None:
        raise ValueError("SKILL_ALREADY_BOUND")

    max_order_row = await _one(
        await db.execute(
            """SELECT COALESCE(MAX(load_order), -1) + 1 AS next_order
               FROM profile_skill_bindings
               WHERE profile_version_id=?""",
            (draft["id"],),
        )
    )
    assert max_order_row is not None
    next_order = max_order_row["next_order"]

    binding_id = _id()
    sha = package_sha256 if len(package_sha256) == 64 else _hashlib.sha256(f"{skill_id}:{skill_version}".encode()).hexdigest()

    await db.execute(
        """INSERT INTO profile_skill_bindings
           (profile_version_id, skill_id, skill_version_id, skill_version,
            package_sha256, load_order)
           VALUES (?,?,?,?,?,?)""",
        (
            draft["id"],
            skill_id,
            binding_id,
            skill_version,
            sha,
            next_order,
        ),
    )

    return {
        "profile_id": profile_id,
        "skill_id": skill_id,
        "skill_version": skill_version,
        "load_order": next_order,
    }


async def unbind_skill(
    db: Any,
    company_id: str,
    profile_id: str,
    *,
    skill_id: str,
) -> dict[str, object]:
    """Remove a skill binding from profile."""
    draft = await _one(
        await db.execute(
            """SELECT v.id FROM employee_base_profile_versions v
               JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE v.profile_id=? AND v.status='draft' AND p.company_id=?""",
            (profile_id, company_id),
        )
    )
    if draft is None:
        raise ValueError("DRAFT_NOT_FOUND")

    cursor = await db.execute(
        """DELETE FROM profile_skill_bindings
           WHERE profile_version_id=? AND skill_id=?""",
        (draft["id"], skill_id),
    )
    if cursor.rowcount == 0:
        raise ValueError("SKILL_NOT_BOUND")

    return {
        "profile_id": profile_id,
        "skill_id": skill_id,
        "unbound": True,
    }


async def validate_draft(
    db: Any,
    company_id: str,
    draft_id: str,
) -> dict[str, object]:
    """Validate draft has required fields."""
    draft = await _one(
        await db.execute(
            """SELECT v.* FROM employee_base_profile_versions v
               JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE v.id=? AND v.status='draft' AND p.company_id=?""",
            (draft_id, company_id),
        )
    )
    if draft is None:
        raise ValueError("DRAFT_NOT_FOUND")

    d = dict(draft)
    errors: list[str] = []
    if not d.get("name"):
        errors.append("missing_name")
    if not d.get("description"):
        errors.append("missing_description")
    if not d.get("system_prompt"):
        errors.append("missing_system_prompt")
    if not d.get("runtime_binding_json"):
        errors.append("missing_runtime_binding")
    if not d.get("catalog_release_id"):
        errors.append("missing_catalog_release")
    try:
        binding = json.loads(d.get("runtime_binding_json") or "{}")
    except (TypeError, ValueError):
        binding = {}
        errors.append("invalid_runtime_binding")
    if d.get("profile_type") == "api_model":
        for field in ("credential_ref", "provider_release_id", "model_binding_id", "provider_protocol"):
            if not isinstance(binding.get(field), str) or not binding[field].strip():
                errors.append(f"missing_{field}")
        try:
            policy = json.loads(d.get("routing_policy_json") or "{}")
        except (TypeError, ValueError):
            policy = None
        try:
            validate_routing_policy(policy if isinstance(policy, dict) else None, profile_type="api_model")
        except ValueError as exc:
            errors.append(str(exc))
        if isinstance(policy, dict) and d.get("catalog_release_id"):
            catalog_errors = await _catalog_policy_errors(db, str(d["catalog_release_id"]), policy)
            errors.extend(catalog_errors)
    elif d.get("profile_type") == "agent_cli" and not str(binding.get("agent_cli", "")).strip():
        errors.append("missing_agent_cli")

    return {
        "draft_id": draft_id,
        "valid": len(errors) == 0,
        "errors": errors,
    }


async def _catalog_policy_errors(db: Any, release_id: str, policy: dict[str, object]) -> list[str]:
    """Validate candidate provider/model bindings against the pinned release."""
    provider_cursor = await db.execute(
        "SELECT content_json FROM catalog_cache_resources WHERE release_id=? AND resource_type='provider'",
        (release_id,),
    )
    providers: list[dict[str, Any]] = []
    for row in await provider_cursor.fetchall():
        try:
            value = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            providers.append(value)
    bindings: dict[str, tuple[str, bool]] = {}
    for provider in providers:
        for binding in provider.get("model_bindings", []):
            if isinstance(binding, dict) and binding.get("binding_id"):
                bindings[str(binding["binding_id"])] = (str(provider.get("id", "")), bool(binding.get("routing_enabled", False)))
    errors: list[str] = []
    raw_candidates = policy.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return errors
    for index, candidate in enumerate(raw_candidates):
        if not isinstance(candidate, dict):
            continue
        binding_id = str(candidate.get("model_binding_id", ""))
        provider_id, enabled = bindings.get(binding_id, ("", False))
        if not provider_id or provider_id != str(candidate.get("provider_release_id", "")):
            errors.append(f"routing_candidate_outside_release:/candidates/{index}")
        if not enabled or not bool(candidate.get("routing_enabled", False)):
            errors.append(f"routing_candidate_disabled:/candidates/{index}")
    return errors


async def publish_draft(
    db: Any,
    company_id: str,
    draft_id: str,
) -> dict[str, object]:
    """Publish draft (draft→published)."""
    now = _now()

    draft = await _one(
        await db.execute(
            """SELECT v.* FROM employee_base_profile_versions v
               JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE v.id=? AND v.status='draft' AND p.company_id=?""",
            (draft_id, company_id),
        )
    )
    if draft is None:
        raise ValueError("DRAFT_NOT_FOUND")

    validation = await validate_draft(db, company_id, draft_id)
    if draft["profile_type"] == "api_model" and not validation["valid"]:
        raise ValueError("PROFILE_NOT_VALID")

    await db.execute(
        """UPDATE employee_base_profile_versions
           SET status='published', published_at=?
           WHERE id=? AND status='draft'
             AND profile_id IN (
                 SELECT id FROM employee_base_profiles WHERE company_id=?
             )""",
        (now, draft_id, company_id),
    )

    await db.execute(
        """UPDATE employee_base_profiles
           SET current_version_id=?, updated_at=?
           WHERE id=? AND company_id=?""",
        (draft_id, now, draft["profile_id"], company_id),
    )

    return {
        "version_id": draft_id,
        "status": "published",
        "published_at": now,
    }


async def retire_version(
    db: Any,
    company_id: str,
    version_id: str,
) -> dict[str, object]:
    """Retire a published version."""
    _now()

    version = await _one(
        await db.execute(
            """SELECT v.* FROM employee_base_profile_versions v
               JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE v.id=? AND v.status='published' AND p.company_id=?""",
            (version_id, company_id),
        )
    )
    if version is None:
        raise ValueError("VERSION_NOT_PUBLISHED")

    await db.execute(
        """UPDATE employee_base_profile_versions
           SET status='retired'
           WHERE id=? AND status='published'
             AND profile_id IN (
                 SELECT id FROM employee_base_profiles WHERE company_id=?
             )""",
        (version_id, company_id),
    )

    return {
        "version_id": version_id,
        "status": "retired",
    }


async def retire_profile(
    db: Any,
    company_id: str,
    profile_id: str,
) -> dict[str, object]:
    """Retire all versions of a profile (rejects drafts, retires published)."""
    now = _now()

    profile = await _one(
        await db.execute(
            "SELECT id FROM employee_base_profiles WHERE id=? AND company_id=?",
            (profile_id, company_id),
        )
    )
    if profile is None:
        raise ValueError("PROFILE_NOT_FOUND")

    draft = await _one(
        await db.execute(
            """SELECT id FROM employee_base_profile_versions
               WHERE profile_id=? AND status='draft'
                 AND profile_id IN (
                     SELECT id FROM employee_base_profiles WHERE company_id=?
                 )""",
            (profile_id, company_id),
        )
    )
    if draft is not None:
        await db.execute(
            """UPDATE employee_base_profile_versions
               SET status='retired'
               WHERE profile_id=? AND status='draft'
                 AND profile_id IN (
                     SELECT id FROM employee_base_profiles WHERE company_id=?
                 )""",
            (profile_id, company_id),
        )

    await db.execute(
        """UPDATE employee_base_profile_versions
           SET status='retired'
           WHERE profile_id=? AND status='published'
             AND profile_id IN (
                 SELECT id FROM employee_base_profiles WHERE company_id=?
             )""",
        (profile_id, company_id),
    )

    await db.execute(
        """UPDATE employee_base_profiles
           SET status='retired', current_version_id=NULL, updated_at=?
           WHERE id=? AND company_id=?""",
        (now, profile_id, company_id),
    )

    return {
        "profile_id": profile_id,
        "status": "retired",
    }
