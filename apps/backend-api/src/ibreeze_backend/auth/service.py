"""Authentication service implementing the G.3/G.5/G.11 contracts."""

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from passlib.hash import argon2
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.token_family import RefreshToken, RefreshTokenFamily
from ibreeze_backend.models.user import User
from ibreeze_backend.observability.logging_config import get_logger
from ibreeze_backend.security.keys import b64url, load_or_create_signing_keys, public_jwk
from ibreeze_backend.settings import settings

logger = get_logger("ibreeze.auth")

APP_AUDIENCE = "ibreeze-desktop"
ADMIN_AUDIENCE = "ibreeze-admin"
OFFLINE_AUDIENCE = "ibreeze-offline"
AUTH_ISSUER = settings.public_origin
ACCESS_TOKEN_SECONDS = 15 * 60
RESTRICTED_ACCESS_TOKEN_SECONDS = 5 * 60
SESSION_SECONDS = 30 * 24 * 60 * 60
MAX_ACTIVE_FAMILIES = 20

password_hasher = argon2.using(
    type="ID",
    memory_cost=65536,
    rounds=3,
    parallelism=4,
    salt_size=16,
    digest_size=32,
)

_private_pem, _public_pem, AUTH_KEY_ID = load_or_create_signing_keys(Path(settings.auth_key_dir))
_private_key = serialization.load_pem_private_key(_private_pem, password=None)
_public_key = _private_key.public_key()


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def user_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "user_type": user.user_type,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "masked_identifier": _masked_identifier(user),
        "status": user.status,
    }


def _masked_identifier(user: User) -> str:
    if user.user_type == "admin":
        username = user.username or ""
        if not username:
            raise ValueError("Invalid admin identifier")
        return f"{username[0]}***"
    email = user.email or ""
    local_part, separator, domain = email.rpartition("@")
    if not separator or not local_part or not domain:
        raise ValueError("Invalid application user email")
    ascii_domain = domain.encode("idna").decode("ascii").lower()
    return f"{local_part[0]}***@{ascii_domain}"


def _encode_jwt(payload: dict[str, object]) -> str:
    return jwt.encode(
        payload,
        _private_pem,
        algorithm="EdDSA",
        headers={"alg": "EdDSA", "typ": "JWT", "kid": AUTH_KEY_ID},
    )


def create_access_token(
    user: User,
    family_id: uuid.UUID,
    audience: str,
) -> str:
    now = datetime.now(UTC)
    lifetime = RESTRICTED_ACCESS_TOKEN_SECONDS if user.must_change_password else ACCESS_TOKEN_SECONDS
    return _encode_jwt(
        {
            "iss": AUTH_ISSUER,
            "aud": audience,
            "sub": str(user.id),
            "user_type": user.user_type,
            "sid": str(family_id),
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now - timedelta(seconds=60),
            "exp": now + timedelta(seconds=lifetime),
            "pwd_change_required": user.must_change_password,
        }
    )


def create_offline_session_ticket(
    user: User,
    device_id: uuid.UUID,
) -> str:
    now = datetime.now(UTC)
    return _encode_jwt(
        {
            "iss": AUTH_ISSUER,
            "aud": OFFLINE_AUDIENCE,
            "sub": str(user.id),
            "device_id": str(device_id),
            "backend_origin": AUTH_ISSUER,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(seconds=SESSION_SECONDS),
        }
    )


def verify_access_token(token: str, expected_audience: str) -> dict[str, Any] | None:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "EdDSA" or header.get("typ") != "JWT" or header.get("kid") != AUTH_KEY_ID:
            return None
        payload = jwt.decode(
            token,
            _public_pem,
            algorithms=["EdDSA"],
            audience=expected_audience,
            issuer=AUTH_ISSUER,
            leeway=60,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "user_type",
                    "sid",
                    "jti",
                    "iat",
                    "nbf",
                    "exp",
                    "pwd_change_required",
                ]
            },
        )
        expected_type = "admin" if expected_audience == ADMIN_AUDIENCE else "app_user"
        if payload.get("user_type") != expected_type or payload.get("type") is not None:
            return None
        return payload
    except (jwt.PyJWTError, ValueError):
        return None


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify an access token for audit-only identity extraction."""
    return verify_access_token(token, APP_AUDIENCE) or verify_access_token(token, ADMIN_AUDIENCE)


async def _revoke_family(
    family: RefreshTokenFamily,
    *,
    reason: str,
    now: datetime | None = None,
) -> None:
    if family.revoked_at is None:
        family.revoked_at = now or datetime.now(UTC)
        family.revoke_reason = reason


async def _revoke_all_user_families(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    reason: str,
) -> None:
    result = await db.execute(
        select(RefreshTokenFamily)
        .where(
            RefreshTokenFamily.user_id == user_id,
            RefreshTokenFamily.revoked_at.is_(None),
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    for family in result.scalars().all():
        await _revoke_family(family, reason=reason, now=now)


async def _enforce_family_limit(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(RefreshTokenFamily)
        .where(
            RefreshTokenFamily.user_id == user_id,
            RefreshTokenFamily.revoked_at.is_(None),
        )
        .order_by(RefreshTokenFamily.last_used_at.asc())
        .with_for_update()
    )
    active = list(result.scalars().all())
    now = datetime.now(UTC)
    for family in active[: max(0, len(active) - MAX_ACTIVE_FAMILIES + 1)]:
        await _revoke_family(family, reason="family_limit", now=now)


async def _create_token_family(
    db: AsyncSession,
    user_id: uuid.UUID,
    device_id: uuid.UUID,
) -> tuple[RefreshTokenFamily, RefreshToken, str]:
    await _enforce_family_limit(db, user_id)
    now = datetime.now(UTC)
    family = RefreshTokenFamily(
        user_id=user_id,
        device_id=device_id,
        created_at=now,
        last_used_at=now,
    )
    db.add(family)
    await db.flush()
    raw_token = _new_refresh_token()
    token = RefreshToken(
        family_id=family.id,
        token_hash=_hash_refresh_token(raw_token),
        issued_at=now,
        expires_at=now + timedelta(seconds=SESSION_SECONDS),
    )
    db.add(token)
    await db.flush()
    return family, token, raw_token


async def register(db: AsyncSession, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    result = await db.execute(select(User.id).where(func.lower(User.email) == normalized_email))
    if result.scalar_one_or_none() is not None:
        raise ValueError("Email already registered")

    user = User(
        user_type="app_user",
        username=None,
        email=normalized_email,
        password_hash=password_hasher.hash(password),
        display_name=normalized_email,
        status="active",
    )
    db.add(user)
    await db.flush()
    logger.info(
        "register_success",
        extra={"user_id": str(user.id), "user_type": user.user_type},
    )
    return user


async def _find_login_user(
    db: AsyncSession,
    identifier: str,
    audience: str,
) -> User | None:
    normalized = identifier.strip().lower()
    condition = (
        func.lower(User.username) == normalized if audience == ADMIN_AUDIENCE else func.lower(User.email) == normalized
    )
    result = await db.execute(select(User).where(condition).with_for_update())
    return result.scalar_one_or_none()


async def login(
    db: AsyncSession,
    identifier: str,
    password: str,
    audience: str,
    device_id: uuid.UUID,
) -> dict[str, object]:
    user = await _find_login_user(db, identifier, audience)
    now = datetime.now(UTC)
    expected_type = "admin" if audience == ADMIN_AUDIENCE else "app_user"

    if (
        user is None
        or user.user_type != expected_type
        or user.status != "active"
        or (user.locked_until is not None and user.locked_until > now)
    ):
        raise ValueError("Invalid credentials")

    if not password_hasher.verify(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_login_count = 0
        raise ValueError("Invalid credentials")

    if password_hasher.needs_update(user.password_hash):
        user.password_hash = password_hasher.hash(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    family, _stored_token, refresh_token = await _create_token_family(db, user.id, device_id)
    return _build_session_result(
        user=user,
        family=family,
        refresh_token=refresh_token,
        audience=audience,
    )


async def admin_login(
    db: AsyncSession,
    username: str,
    password: str,
    device_id: uuid.UUID,
) -> dict[str, object]:
    return await login(db, username, password, ADMIN_AUDIENCE, device_id)


def _build_session_result(
    *,
    user: User,
    family: RefreshTokenFamily,
    refresh_token: str,
    audience: str,
) -> dict[str, object]:
    result: dict[str, object] = {
        "user": user_payload(user),
        "access_token": create_access_token(user, family.id, audience),
        "access_token_expires_in": (
            RESTRICTED_ACCESS_TOKEN_SECONDS if user.must_change_password else ACCESS_TOKEN_SECONDS
        ),
        "family_id": family.id,
        "pwd_change_required": user.must_change_password,
        "refresh_token": refresh_token,
        "refresh_token_expires_in": SESSION_SECONDS,
    }
    if audience == APP_AUDIENCE and not user.must_change_password:
        result["offline_session_ticket"] = create_offline_session_ticket(user, family.device_id)
        result["offline_session_ticket_expires_in"] = SESSION_SECONDS
    return result


async def refresh_tokens(
    db: AsyncSession,
    refresh_token_raw: str,
    expected_audience: str,
) -> dict[str, object]:
    token_hash = _hash_refresh_token(refresh_token_raw)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update())
    stored_token = result.scalar_one_or_none()
    if stored_token is None:
        raise ValueError("Invalid refresh token")

    family_result = await db.execute(
        select(RefreshTokenFamily).where(RefreshTokenFamily.id == stored_token.family_id).with_for_update()
    )
    family = family_result.scalar_one()
    now = datetime.now(UTC)
    if (
        family.revoked_at is not None
        or stored_token.revoked_at is not None
        or stored_token.expires_at <= now
        or stored_token.consumed_at is not None
    ):
        await _revoke_family(family, reason="replay_detected", now=now)
        raise ValueError("Refresh token replay detected")

    user_result = await db.execute(select(User).where(User.id == family.user_id).with_for_update())
    user = user_result.scalar_one_or_none()
    expected_type = "admin" if expected_audience == ADMIN_AUDIENCE else "app_user"
    if user is None or user.status != "active" or user.user_type != expected_type:
        await _revoke_family(family, reason="invalid_user", now=now)
        raise ValueError("Invalid refresh token")

    raw_replacement = _new_refresh_token()
    replacement = RefreshToken(
        family_id=family.id,
        token_hash=_hash_refresh_token(raw_replacement),
        issued_at=now,
        expires_at=now + timedelta(seconds=SESSION_SECONDS),
    )
    db.add(replacement)
    await db.flush()
    stored_token.consumed_at = now
    stored_token.replaced_by_id = replacement.id
    family.last_used_at = now
    return _build_session_result(
        user=user,
        family=family,
        refresh_token=raw_replacement,
        audience=expected_audience,
    )


async def logout(
    db: AsyncSession,
    access_token: str,
    expected_audience: str,
) -> bool:
    payload = verify_access_token(access_token, expected_audience)
    if payload is None:
        return False
    result = await db.execute(
        select(RefreshTokenFamily).where(RefreshTokenFamily.id == uuid.UUID(payload["sid"])).with_for_update()
    )
    family = result.scalar_one_or_none()
    if family is None:
        return False
    await _revoke_family(family, reason="logout")
    return True


async def logout_all(db: AsyncSession, user_id: uuid.UUID) -> None:
    await _revoke_all_user_families(db, user_id, reason="logout_all")


async def change_password(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_password: str,
    new_password: str,
    current_family_id: uuid.UUID,
    audience: str,
) -> dict[str, object]:
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if user is None or not password_hasher.verify(current_password, user.password_hash):
        raise ValueError("Invalid password")

    family_result = await db.execute(
        select(RefreshTokenFamily).where(RefreshTokenFamily.id == current_family_id).with_for_update()
    )
    current_family = family_result.scalar_one_or_none()
    if current_family is None or current_family.user_id != user.id:
        raise ValueError("Invalid session")
    device_id = current_family.device_id

    user.password_hash = password_hasher.hash(new_password)
    user.must_change_password = False
    user.version += 1
    user.updated_at = datetime.now(UTC)
    await _revoke_all_user_families(db, user.id, reason="password_changed")
    new_family, _stored_token, raw_token = await _create_token_family(db, user.id, device_id)
    return _build_session_result(
        user=user,
        family=new_family,
        refresh_token=raw_token,
        audience=audience,
    )


def get_auth_keys() -> dict[str, object]:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=24)
    keys: list[dict[str, object]] = [public_jwk(_public_pem, AUTH_KEY_ID)]
    signed_payload = {
        "keys": keys,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    canonical = json.dumps(signed_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    catalog_private_pem, _catalog_public_pem, catalog_key_id = load_or_create_signing_keys(
        Path(settings.catalog_key_dir)
    )
    catalog_private_key = serialization.load_pem_private_key(catalog_private_pem, password=None)
    signature = catalog_private_key.sign(canonical)
    return {
        **signed_payload,
        "signing_key_id": catalog_key_id,
        "signature_algorithm": "Ed25519",
        "signature": b64url(signature),
    }
