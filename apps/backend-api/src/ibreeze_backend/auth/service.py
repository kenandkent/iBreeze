"""Authentication service – aligned with G.3 token family schema."""
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from passlib.hash import argon2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.token_family import RefreshToken, RefreshTokenFamily
from ibreeze_backend.models.user import User
from ibreeze_backend.settings import settings

_private_key = Ed25519PrivateKey.generate()
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_public_key = _private_key.public_key()
_public_pem = _public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


def create_access_token(
    user_id: str, family_id: str, audience: str, pwd_change_required: bool = False
) -> str:
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "family": family_id,
        "aud": audience,
        "exp": expire,
        "pwd_change_required": pwd_change_required,
    }
    return jwt.encode(payload, _private_pem, algorithm="EdDSA")


def create_refresh_token(user_id: str, family_id: str, audience: str) -> str:
    expire = datetime.now(UTC) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": user_id,
        "family": family_id,
        "aud": audience,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, _private_pem, algorithm="EdDSA")


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            _public_pem,
            algorithms=["EdDSA"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def create_token_family(
    db: AsyncSession,
    user_id: uuid.UUID,
    refresh_token_hash: str | None = None,
    family_id: str | None = None,
) -> RefreshTokenFamily:
    fid = uuid.UUID(family_id) if family_id else uuid.uuid4()
    family = RefreshTokenFamily(
        id=fid,
        user_id=user_id,
        device_id=uuid.uuid4(),
        created_at=_now_iso(),
    )
    db.add(family)

    if refresh_token_hash:
        rt = RefreshToken(
            id=uuid.uuid4(),
            family_id=fid,
            token_hash=refresh_token_hash,
            issued_at=_now_iso(),
            expires_at=(datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)).isoformat(),
        )
        db.add(rt)

    await db.flush()
    return family


async def _revoke_all_user_families(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(RefreshTokenFamily).where(
            RefreshTokenFamily.user_id == user_id,
            RefreshTokenFamily.revoked_at.is_(None),
        )
    )
    for family in result.scalars().all():
        family.revoked_at = _now_iso()
        family.revoke_reason = "replay_detected"


async def register(db: AsyncSession, email: str, password: str) -> User:
    normalized_email = email.strip().lower()

    result = await db.execute(select(User).where(User.email == normalized_email))
    if result.scalar_one_or_none():
        raise ValueError("Email already registered")

    base_username = normalized_email.split("@")[0][:64]
    username = base_username
    counter = 1
    while True:
        result = await db.execute(select(User).where(User.username == username))
        if not result.scalar_one_or_none():
            break
        username = f"{base_username[:58]}_{counter}"[:64]
        counter += 1

    user = User(
        username=username,
        email=normalized_email,
        hashed_password=argon2.hash(password),
        user_type="app_user",
    )
    db.add(user)
    await db.flush()
    return user


async def login(
    db: AsyncSession, email: str, password: str, audience: str
) -> dict:
    normalized_email = email.strip().lower()

    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()

    if not user or not argon2.verify(password, user.hashed_password):
        raise ValueError("Invalid credentials")

    if not user.is_active:
        raise ValueError("Invalid credentials")

    expected_user_type = "admin" if audience == "admin" else "app_user"
    if user.user_type != expected_user_type:
        raise ValueError("Invalid credentials")

    family_id = str(uuid.uuid4())
    refresh_token = create_refresh_token(str(user.id), family_id, audience)
    refresh_token_hash = argon2.hash(refresh_token)

    family = await create_token_family(db, user.id, refresh_token_hash, family_id)

    access_token = create_access_token(
        str(user.id), family.family_id, audience, user.must_change_password
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_type": user.user_type,
        "pwd_change_required": user.must_change_password,
    }


async def admin_login(db: AsyncSession, email: str, password: str) -> dict:
    result = await login(db, email, password, "admin")
    del result["pwd_change_required"]
    return result


async def refresh_tokens(db: AsyncSession, refresh_token_raw: str) -> dict:
    payload = verify_token(refresh_token_raw)
    if not payload or payload.get("type") != "refresh":
        raise ValueError("Invalid refresh token")

    family_id = payload.get("family")
    user_id = payload.get("sub")
    audience = payload.get("aud")

    if not family_id or not user_id:
        raise ValueError("Invalid refresh token")

    result = await db.execute(
        select(RefreshTokenFamily).where(
            RefreshTokenFamily.id == uuid.UUID(family_id),
            RefreshTokenFamily.revoked_at.is_(None),
        )
    )
    family = result.scalar_one_or_none()

    if not family:
        await _revoke_all_user_families(db, uuid.UUID(user_id))
        raise ValueError("Refresh token replay detected")

    rt_result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family.id,
            RefreshToken.consumed_at.is_(None),
            RefreshToken.revoked_at.is_(None),
        )
    )
    stored_rt = rt_result.scalar_one_or_none()
    if stored_rt and stored_rt.token_hash:
        if not argon2.verify(refresh_token_raw, stored_rt.token_hash):
            await _revoke_all_user_families(db, uuid.UUID(user_id))
            raise ValueError("Refresh token replay detected")
        stored_rt.consumed_at = _now_iso()

    family.revoked_at = _now_iso()
    family.revoke_reason = "rotated"

    new_family_id = str(uuid.uuid4())
    new_refresh_token = create_refresh_token(user_id, new_family_id, audience)
    new_refresh_token_hash = argon2.hash(new_refresh_token)

    new_family = await create_token_family(db, uuid.UUID(user_id), new_refresh_token_hash, new_family_id)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    access_token = create_access_token(
        user_id, new_family.family_id, audience, user.must_change_password
    )

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


async def logout(db: AsyncSession, access_token: str) -> bool:
    payload = verify_token(access_token)
    if not payload:
        return False

    family_id = payload.get("family")
    if not family_id:
        return False

    result = await db.execute(
        select(RefreshTokenFamily).where(RefreshTokenFamily.id == uuid.UUID(family_id))
    )
    family = result.scalar_one_or_none()
    if not family:
        return False

    family.revoked_at = _now_iso()
    family.revoke_reason = "logout"
    return True


async def logout_all(db: AsyncSession, user_id: uuid.UUID) -> bool:
    await _revoke_all_user_families(db, user_id)
    return True


async def change_password(
    db: AsyncSession, user_id: uuid.UUID, old_password: str, new_password: str
) -> dict:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    if not argon2.verify(old_password, user.hashed_password):
        raise ValueError("Invalid password")

    user.hashed_password = argon2.hash(new_password)
    user.must_change_password = False

    await _revoke_all_user_families(db, user_id)

    family_id = str(uuid.uuid4())
    audience = "admin" if user.user_type == "admin" else "app"
    refresh_token = create_refresh_token(str(user_id), family_id, audience)
    refresh_token_hash = argon2.hash(refresh_token)

    family = await create_token_family(db, user_id, refresh_token_hash, family_id)

    access_token = create_access_token(str(user_id), family.family_id, audience, False)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def get_auth_keys() -> dict:
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "ibreeze-key-1",
                "use": "sig",
            }
        ]
    }
