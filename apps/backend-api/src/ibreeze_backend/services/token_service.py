"""Token service for JWT token management with rotation and family tracking."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.auth.service import create_access_token, verify_token
from ibreeze_backend.models.token_family import RefreshTokenFamily as TokenFamily

__all__ = [
    "create_access_token",
    "verify_token",
    "create_token_family",
    "rotate_token",
    "revoke_family",
]


async def create_token_family(db: AsyncSession, user_id: uuid.UUID, refresh_token_hash: str | None = None) -> TokenFamily:
    """Create a new token family for a user."""
    family = TokenFamily(
        user_id=user_id,
        family_id=str(uuid.uuid4()),
        status="active",
        refresh_token_hash=refresh_token_hash,
    )
    db.add(family)
    await db.flush()
    return family


async def rotate_token(
    db: AsyncSession, old_token: str
) -> tuple[str, TokenFamily] | None:
    """Rotate a token. Returns new token and family, or None if invalid."""
    payload = verify_token(old_token)
    if not payload:
        return None

    family_id = payload.get("family")
    if not family_id:
        return None

    result = await db.execute(
        select(TokenFamily).where(
            TokenFamily.family_id == family_id,
            TokenFamily.status == "active",
        )
    )
    family = result.scalar_one_or_none()
    if not family:
        return None

    family.status = "rotated"
    family.rotated_at = datetime.now(UTC)

    new_family = await create_token_family(db, family.user_id)
    audience = payload.get("aud", "app")
    new_token = create_access_token(str(family.user_id), new_family.family_id, audience)

    return new_token, new_family


async def revoke_family(db: AsyncSession, family_id: str) -> bool:
    """Revoke a token family."""
    result = await db.execute(
        select(TokenFamily).where(TokenFamily.family_id == family_id)
    )
    family = result.scalar_one_or_none()
    if not family:
        return False
    family.status = "revoked"
    return True
