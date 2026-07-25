"""Employee base profile management service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


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
) -> dict[str, object]:
    """Create a new profile draft version."""
    profile_id = _id()
    version_id = _id()
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        existing = await _one(
            await db.execute(
                """SELECT id FROM employee_base_profile_versions
                   WHERE profile_id=? AND company_id=? AND status='draft'""",
                (profile_id, company_id),
            )
        )
        if existing is not None:
            raise ValueError("DRAFT_ALREADY_EXISTS")

        normalized_name = base_profile.get("name", "").strip().lower()

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
                runtime_binding_json, system_prompt, capability_tags_json,
                tool_policy_json, timeout_seconds, max_retries,
                workspace_policy, catalog_release_id, content_sha256,
                status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                version_id,
                profile_id,
                1,
                base_profile.get("name", ""),
                base_profile.get("description", ""),
                "agent_cli" if agent_cli else "api_model",
                json.dumps({"agent_cli": agent_cli, "api_model": api_model}),
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

        await db.commit()
        return {
            "profile_id": profile_id,
            "version_id": version_id,
            "status": "draft",
        }
    except Exception:
        await db.rollback()
        raise


async def update_draft(
    db: Any,
    company_id: str,
    draft_id: str,
    *,
    agent_cli: str,
    api_model: str,
) -> dict[str, object]:
    """Update an existing draft."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        draft = await _one(
            await db.execute(
                """SELECT * FROM employee_base_profile_versions
                   WHERE id=? AND company_id=? AND status='draft'""",
                (draft_id, company_id),
            )
        )
        if draft is None:
            raise ValueError("DRAFT_NOT_FOUND")

        await db.execute(
            """UPDATE employee_base_profile_versions
               SET runtime_binding_json=?, updated_at=?
               WHERE id=? AND company_id=? AND status='draft'""",
            (
                json.dumps({"agent_cli": agent_cli, "api_model": api_model}),
                now,
                draft_id,
                company_id,
            ),
        )

        await db.commit()
        return {
            "version_id": draft_id,
            "status": "draft",
            "updated_at": now,
        }
    except Exception:
        await db.rollback()
        raise


async def get_profile(
    db: Any,
    company_id: str,
    profile_id: str,
) -> dict[str, object] | None:
    """Return profile with versions."""
    profile = await _one(
        await db.execute(
            "SELECT * FROM employee_base_profiles WHERE id=?",
            (profile_id,),
        )
    )
    if profile is None:
        return None

    cursor = await db.execute(
        """SELECT * FROM employee_base_profile_versions
           WHERE profile_id=? AND company_id=?
           ORDER BY version_number DESC""",
        (profile_id, company_id),
    )
    versions = [dict(row) for row in await cursor.fetchall()]

    return {**dict(profile), "versions": versions}


async def list_profiles(
    db: Any,
    company_id: str,
    *,
    employee_id: str | None = None,
) -> list[dict[str, object]]:
    """List all profiles, optional filter by employee."""
    conditions = ["company_id=?"]
    params: list[Any] = [company_id]

    if employee_id is not None:
        conditions.append("employee_id=?")
        params.append(employee_id)

    where = " AND ".join(conditions)

    cursor = await db.execute(
        f"""SELECT * FROM employee_base_profiles
            WHERE {where}
            ORDER BY created_at DESC, id DESC""",
        tuple(params),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def bind_skill(
    db: Any,
    company_id: str,
    profile_id: str,
    *,
    skill_id: str,
    skill_version: str,
) -> dict[str, object]:
    """Bind a skill to profile."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        draft = await _one(
            await db.execute(
                """SELECT id FROM employee_base_profile_versions
                   WHERE profile_id=? AND company_id=? AND status='draft'""",
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
        next_order = max_order_row["next_order"]

        binding_id = _id()
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
                "",
                next_order,
            ),
        )

        await db.commit()
        return {
            "profile_id": profile_id,
            "skill_id": skill_id,
            "skill_version": skill_version,
            "load_order": next_order,
        }
    except Exception:
        await db.rollback()
        raise


async def unbind_skill(
    db: Any,
    company_id: str,
    profile_id: str,
    *,
    skill_id: str,
) -> dict[str, object]:
    """Remove a skill binding from profile."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        draft = await _one(
            await db.execute(
                """SELECT id FROM employee_base_profile_versions
                   WHERE profile_id=? AND company_id=? AND status='draft'""",
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

        await db.commit()
        return {
            "profile_id": profile_id,
            "skill_id": skill_id,
            "unbound": True,
        }
    except Exception:
        await db.rollback()
        raise


async def validate_draft(
    db: Any,
    company_id: str,
    draft_id: str,
) -> dict[str, object]:
    """Validate draft has required fields."""
    draft = await _one(
        await db.execute(
            """SELECT * FROM employee_base_profile_versions
               WHERE id=? AND company_id=? AND status='draft'""",
            (draft_id, company_id),
        )
    )
    if draft is None:
        raise ValueError("DRAFT_NOT_FOUND")

    errors: list[str] = []
    if not draft.get("name"):
        errors.append("missing_name")
    if not draft.get("description"):
        errors.append("missing_description")
    if not draft.get("system_prompt"):
        errors.append("missing_system_prompt")
    if not draft.get("runtime_binding_json"):
        errors.append("missing_runtime_binding")
    if not draft.get("catalog_release_id"):
        errors.append("missing_catalog_release")

    return {
        "draft_id": draft_id,
        "valid": len(errors) == 0,
        "errors": errors,
    }


async def publish_draft(
    db: Any,
    company_id: str,
    draft_id: str,
) -> dict[str, object]:
    """Publish draft (draft→published)."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        draft = await _one(
            await db.execute(
                """SELECT * FROM employee_base_profile_versions
                   WHERE id=? AND company_id=? AND status='draft'""",
                (draft_id, company_id),
            )
        )
        if draft is None:
            raise ValueError("DRAFT_NOT_FOUND")

        await db.execute(
            """UPDATE employee_base_profile_versions
               SET status='published', published_at=?
               WHERE id=? AND company_id=? AND status='draft'""",
            (now, draft_id, company_id),
        )

        await db.execute(
            """UPDATE employee_base_profiles
               SET current_version_id=?, updated_at=?
               WHERE id=?""",
            (draft_id, now, draft["profile_id"]),
        )

        await db.commit()
        return {
            "version_id": draft_id,
            "status": "published",
            "published_at": now,
        }
    except Exception:
        await db.rollback()
        raise


async def retire_version(
    db: Any,
    company_id: str,
    version_id: str,
) -> dict[str, object]:
    """Retire a published version."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        version = await _one(
            await db.execute(
                """SELECT * FROM employee_base_profile_versions
                   WHERE id=? AND company_id=? AND status='published'""",
                (version_id, company_id),
            )
        )
        if version is None:
            raise ValueError("VERSION_NOT_PUBLISHED")

        await db.execute(
            """UPDATE employee_base_profile_versions
               SET status='retired'
               WHERE id=? AND company_id=? AND status='published'""",
            (version_id, company_id),
        )

        await db.commit()
        return {
            "version_id": version_id,
            "status": "retired",
        }
    except Exception:
        await db.rollback()
        raise


async def retire_profile(
    db: Any,
    company_id: str,
    profile_id: str,
) -> dict[str, object]:
    """Retire all versions of a profile."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        profile = await _one(
            await db.execute(
                "SELECT id FROM employee_base_profiles WHERE id=?",
                (profile_id,),
            )
        )
        if profile is None:
            raise ValueError("PROFILE_NOT_FOUND")

        await db.execute(
            """UPDATE employee_base_profile_versions
               SET status='retired'
               WHERE profile_id=? AND company_id=?
               AND status IN ('draft', 'published')""",
            (profile_id, company_id),
        )

        await db.execute(
            """UPDATE employee_base_profiles
               SET status='retired', current_version_id=NULL, updated_at=?
               WHERE id=?""",
            (now, profile_id),
        )

        await db.commit()
        return {
            "profile_id": profile_id,
            "status": "retired",
        }
    except Exception:
        await db.rollback()
        raise
