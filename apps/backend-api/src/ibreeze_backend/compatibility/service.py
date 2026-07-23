"""Compatibility rule service with evaluation logic."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.compatibility.models import CompatibilityRule


async def create_rule(
    db: AsyncSession,
    subject_type: str,
    subject_version_range: dict | None,
    dependency_type: str,
    dependency_version_range: dict | None,
    result: str,
    reason_code: str | None,
    priority: int,
) -> CompatibilityRule:
    rule = CompatibilityRule(
        subject_type=subject_type,
        subject_version_range=subject_version_range,
        dependency_type=dependency_type,
        dependency_version_range=dependency_version_range,
        result=result,
        reason_code=reason_code,
        priority=priority,
    )
    db.add(rule)
    await db.flush()
    return rule


async def get_rule(
    db: AsyncSession, rule_id: uuid.UUID
) -> CompatibilityRule | None:
    result = await db.execute(
        select(CompatibilityRule).where(CompatibilityRule.id == rule_id)
    )
    return result.scalar_one_or_none()


async def list_rules(
    db: AsyncSession, skip: int, limit: int
) -> tuple[list[CompatibilityRule], int]:
    count_result = await db.execute(
        select(func.count(CompatibilityRule.id))
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(CompatibilityRule)
        .order_by(
            CompatibilityRule.priority.desc(),
            CompatibilityRule.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def update_rule(
    db: AsyncSession,
    rule_id: uuid.UUID,
    subject_type: str | None,
    subject_version_range: dict | None,
    dependency_type: str | None,
    dependency_version_range: dict | None,
    result: str | None,
    reason_code: str | None,
    priority: int | None,
) -> CompatibilityRule:
    rule = await get_rule(db, rule_id)
    if not rule:
        raise ValueError("Rule not found")

    if subject_type is not None:
        rule.subject_type = subject_type
    if subject_version_range is not None:
        rule.subject_version_range = subject_version_range
    if dependency_type is not None:
        rule.dependency_type = dependency_type
    if dependency_version_range is not None:
        rule.dependency_version_range = dependency_version_range
    if result is not None:
        rule.result = result
    if reason_code is not None:
        rule.reason_code = reason_code
    if priority is not None:
        rule.priority = priority

    await db.flush()
    return rule


async def delete_rule(db: AsyncSession, rule_id: uuid.UUID) -> None:
    rule = await get_rule(db, rule_id)
    if not rule:
        raise ValueError("Rule not found")
    await db.delete(rule)
    await db.flush()


def _version_in_range(
    version: str | None, version_range: dict | None
) -> bool:
    if not version_range:
        return True
    if not version:
        return True

    min_v = version_range.get("min")
    max_v = version_range.get("max")

    if min_v and version < min_v:
        return False
    if max_v and version >= max_v:
        return False
    return True


async def evaluate(
    db: AsyncSession,
    subject_type: str,
    subject_version: str | None,
    dependency_type: str,
    dependency_version: str | None,
) -> tuple[str, str | None, str | None]:
    result = await db.execute(
        select(CompatibilityRule).where(
            CompatibilityRule.subject_type == subject_type,
            CompatibilityRule.dependency_type == dependency_type,
        )
    )
    rules = list(result.scalars().all())

    matched = []
    for rule in rules:
        if not _version_in_range(subject_version, rule.subject_version_range):
            continue
        if not _version_in_range(
            dependency_version, rule.dependency_version_range
        ):
            continue
        matched.append(rule)

    if not matched:
        return "allow", None, None

    matched.sort(key=lambda r: r.priority, reverse=True)

    highest_priority = matched[0].priority
    top_rules = [r for r in matched if r.priority == highest_priority]

    deny_rules = [r for r in top_rules if r.result == "deny"]
    if deny_rules:
        winner = deny_rules[0]
        return winner.result, winner.reason_code, str(winner.id)

    winner = top_rules[0]
    return winner.result, winner.reason_code, str(winner.id)
