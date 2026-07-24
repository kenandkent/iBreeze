"""Compatibility rule state machine."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.compatibility.models import CompatibilityRule
from ibreeze_backend.compatibility.schemas import RuleCreate, RuleUpdate

_VERSION_RANGE = re.compile(r"^[0-9A-Za-z.*<>=~^|+\-\s]+$")


def _validate_version_range(value: str) -> None:
    if not _VERSION_RANGE.fullmatch(value) or not any(character.isdigit() for character in value):
        raise ValueError("COMPATIBILITY_VERSION_RANGE_INVALID")


async def create_rule(db: AsyncSession, body: RuleCreate) -> CompatibilityRule:
    item = CompatibilityRule(**body.model_dump(), status="draft", version=1)
    db.add(item)
    await db.flush()
    return item


async def get_rule(db: AsyncSession, rule_id: uuid.UUID) -> CompatibilityRule | None:
    result = await db.execute(select(CompatibilityRule).where(CompatibilityRule.id == rule_id))
    return result.scalar_one_or_none()


async def list_rules(db: AsyncSession, limit: int = 50) -> list[CompatibilityRule]:
    return list(
        await db.scalars(
            select(CompatibilityRule)
            .order_by(CompatibilityRule.created_at.desc())
            .limit(limit)
        )
    )


async def update_rule(
    db: AsyncSession,
    rule_id: uuid.UUID,
    body: RuleUpdate,
    expected_version: int,
) -> CompatibilityRule:
    item = await _locked_rule(db, rule_id)
    _assert_mutable(item)
    if item.version != expected_version:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(item, name, value)
    item.status = "draft"
    item.version += 1
    await db.flush()
    return item


async def delete_rule(
    db: AsyncSession,
    rule_id: uuid.UUID,
    expected_version: int,
) -> None:
    item = await _locked_rule(db, rule_id)
    _assert_mutable(item)
    if item.version != expected_version:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    await db.delete(item)
    await db.flush()


async def validate_rule(db: AsyncSession, rule_id: uuid.UUID) -> CompatibilityRule:
    item = await _locked_rule(db, rule_id)
    _assert_mutable(item)
    _validate_version_range(item.subject_version_range)
    _validate_version_range(item.dependency_version_range)
    item.status = "validated"
    await db.flush()
    return item


async def _locked_rule(db: AsyncSession, rule_id: uuid.UUID) -> CompatibilityRule:
    result = await db.execute(
        select(CompatibilityRule)
        .where(CompatibilityRule.id == rule_id)
        .with_for_update()
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise ValueError("CATALOG_RESOURCE_NOT_FOUND")
    return item


def _assert_mutable(item: CompatibilityRule) -> None:
    if item.status == "published":
        raise ValueError("CATALOG_REVISION_IMMUTABLE")
