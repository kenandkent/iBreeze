"""Authentication service."""
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from passlib.hash import argon2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.token_family import TokenFamily
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


async def create_token_family(db: AsyncSession, user_id: uuid.UUID) -> TokenFamily:
    family = TokenFamily(
        user_id=user_id,
        family_id=str(uuid.uuid4()),
        status="active",
    )
    db.add(family)
    await db.flush()
    return family


async def _revoke_all_user_families(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(TokenFamily).where(
            TokenFamily.user_id == user_id,
            TokenFamily.status == "active",
        )
    )
    for family in result.scalars().all():
        family.status = "revoked"


async def register(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError("Email already registered")

    base_username = email.split("@")[0][:64]
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
        email=email,
        hashed_password=argon2.hash(password),
        user_type="app_user",
    )
    db.add(user)
    await db.flush()
    return user


async def login(
    db: AsyncSession, email: str, password: str, audience: str
) -> dict:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not argon2.verify(password, user.hashed_password):
        raise ValueError("Invalid credentials")

    if not user.is_active:
        raise ValueError("Account is disabled")

    expected_user_type = "admin" if audience == "admin" else "app_user"
    if user.user_type != expected_user_type:
        raise ValueError("Invalid credentials")

    family = await create_token_family(db, user.id)
    access_token = create_access_token(
        str(user.id), family.family_id, audience, user.must_change_password
    )
    refresh_token = create_refresh_token(str(user.id), family.family_id, audience)

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
        select(TokenFamily).where(
            TokenFamily.family_id == family_id,
            TokenFamily.status == "active",
        )
    )
    family = result.scalar_one_or_none()

    if not family:
        await _revoke_all_user_families(db, uuid.UUID(user_id))
        raise ValueError("Refresh token replay detected")

    family.status = "rotated"
    family.rotated_at = datetime.now(UTC)

    new_family = await create_token_family(db, uuid.UUID(user_id))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    access_token = create_access_token(
        user_id, new_family.family_id, audience, user.must_change_password
    )
    new_refresh_token = create_refresh_token(user_id, new_family.family_id, audience)

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
        select(TokenFamily).where(TokenFamily.family_id == family_id)
    )
    family = result.scalar_one_or_none()
    if not family:
        return False

    family.status = "revoked"
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

    family = await create_token_family(db, user_id)
    audience = "admin" if user.user_type == "admin" else "app"

    access_token = create_access_token(str(user_id), family.family_id, audience, False)
    refresh_token = create_refresh_token(str(user_id), family.family_id, audience)

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
