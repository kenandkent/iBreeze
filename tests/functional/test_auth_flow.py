"""Auth flow tests — JWT creation, verification, token families, rotation, revocation.

Covers design spec sections:
- G.11 Authentication (access token, refresh token families, rotation, revocation)
- Token algorithm, expiry, payload structure
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Token creation & verification
# ---------------------------------------------------------------------------

class TestTokenCreation:
    """JWT access token creation."""

    def test_create_access_token_returns_string(self):
        from ibreeze_backend.services.token_service import create_access_token

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_access_token_contains_valid_jwt_structure(self):
        from ibreeze_backend.services.token_service import create_access_token

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        parts = token.split(".")
        assert len(parts) == 3, "JWT must have header.payload.signature"

    def test_create_access_token_payload_has_sub_and_family(self):
        from ibreeze_backend.services.token_service import (
            create_access_token,
            verify_token,
        )

        user_id = str(uuid.uuid4())
        family_id = str(uuid.uuid4())
        token = create_access_token(user_id, family_id, "admin")
        payload = verify_token(token)

        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["family"] == family_id

    def test_create_access_token_expiry_in_future(self):
        from ibreeze_backend.services.token_service import (
            create_access_token,
            verify_token,
        )

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        payload = verify_token(token)
        assert payload is not None
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)

    def test_create_access_token_uses_configured_algorithm(self):
        from ibreeze_backend.settings import settings
        from ibreeze_backend.services.token_service import create_access_token

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        import jwt as _jwt_mod
        header = _jwt_mod.get_unverified_header(token)
        assert header["alg"] == settings.token_algorithm


class TestTokenVerification:
    """JWT token verification."""

    def test_verify_valid_token(self):
        from ibreeze_backend.services.token_service import (
            create_access_token,
            verify_token,
        )

        uid = str(uuid.uuid4())
        fid = str(uuid.uuid4())
        token = create_access_token(uid, fid, "admin")
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == uid

    def test_verify_invalid_token_returns_none(self):
        from ibreeze_backend.services.token_service import verify_token

        assert verify_token("not.a.valid.token") is None

    def test_verify_tampered_token_returns_none(self):
        from ibreeze_backend.services.token_service import (
            create_access_token,
            verify_token,
        )

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B") + "." + parts[2]
        assert verify_token(tampered) is None

    def test_verify_empty_string_returns_none(self):
        from ibreeze_backend.services.token_service import verify_token

        assert verify_token("") is None

    def test_verify_token_with_wrong_secret_returns_none(self):
        from ibreeze_backend.services.token_service import verify_token

        import jwt
        payload = {"sub": "user1", "family": "fam1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        assert verify_token(token) is None


class TestTokenExpiry:
    """Token expiry edge cases."""

    def test_expired_token_returns_none(self):
        from ibreeze_backend.services.token_service import verify_token
        from ibreeze_backend.auth.service import _private_pem
        import jwt

        payload = {
            "sub": str(uuid.uuid4()),
            "family": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(payload, _private_pem, algorithm="EdDSA")
        assert verify_token(token) is None

    def test_token_near_expiry_still_valid(self):
        from ibreeze_backend.services.token_service import (
            create_access_token,
            verify_token,
        )

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        payload = verify_token(token)
        assert payload is not None
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        from ibreeze_backend.settings import settings
        expected_exp = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
        diff = abs((exp - expected_exp).total_seconds())
        assert diff < 5, f"Expiry should be ~{settings.token_expire_minutes}min from now, diff={diff}s"


# ---------------------------------------------------------------------------
# Token families
# ---------------------------------------------------------------------------

class TestTokenFamily:
    """Token family creation and lifecycle."""

    @pytest.mark.asyncio
    async def test_create_token_family(self, mock_db_session):
        from ibreeze_backend.services.token_service import create_token_family

        user_id = uuid.uuid4()
        family = await create_token_family(mock_db_session, user_id)

        assert family.user_id == user_id
        assert family.family_id is not None
        assert len(family.family_id) == 36  # UUID format
        assert family.status == "active"
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_multiple_families_unique_ids(self, mock_db_session):
        from ibreeze_backend.services.token_service import create_token_family

        user_id = uuid.uuid4()
        f1 = await create_token_family(mock_db_session, user_id)
        f2 = await create_token_family(mock_db_session, user_id)
        assert f1.family_id != f2.family_id


class TestTokenRotation:
    """Token rotation (refresh flow)."""

    @pytest.mark.asyncio
    async def test_rotate_valid_active_token(self, mock_db_session):
        from ibreeze_backend.services.token_service import (
            create_access_token,
            rotate_token,
        )
        from ibreeze_backend.models.token_family import TokenFamily

        user_id = uuid.uuid4()
        family_id = str(uuid.uuid4())

        old_family = MagicMock(spec=TokenFamily)
        old_family.user_id = user_id
        old_family.family_id = family_id
        old_family.status = "active"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = old_family
        mock_db_session.execute.return_value = mock_result

        old_token = create_access_token(str(user_id), family_id, "admin")
        result = await rotate_token(mock_db_session, old_token)

        assert result is not None
        new_token, new_family = result
        assert isinstance(new_token, str)
        assert new_token != old_token
        assert old_family.status == "rotated"
        assert old_family.rotated_at is not None

    @pytest.mark.asyncio
    async def test_rotate_invalid_token_returns_none(self, mock_db_session):
        from ibreeze_backend.services.token_service import rotate_token

        result = await rotate_token(mock_db_session, "invalid.token.here")
        assert result is None

    @pytest.mark.asyncio
    async def test_rotate_token_with_no_family_returns_none(self, mock_db_session):
        from ibreeze_backend.services.token_service import rotate_token
        from ibreeze_backend.auth.service import _private_pem
        import jwt

        payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, _private_pem, algorithm="EdDSA")
        result = await rotate_token(mock_db_session, token)
        assert result is None

    @pytest.mark.asyncio
    async def test_rotate_token_with_nonexistent_family_returns_none(self, mock_db_session):
        from ibreeze_backend.services.token_service import rotate_token, create_access_token

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await rotate_token(mock_db_session, token)
        assert result is None

    @pytest.mark.asyncio
    async def test_rotate_already_rotated_family_returns_none(self, mock_db_session):
        from ibreeze_backend.services.token_service import rotate_token, create_access_token
        from ibreeze_backend.models.token_family import TokenFamily

        family = MagicMock(spec=TokenFamily)
        family.family_id = str(uuid.uuid4())
        family.status = "rotated"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        token = create_access_token(str(uuid.uuid4()), family.family_id, "admin")
        result = await rotate_token(mock_db_session, token)
        assert result is None


class TestTokenRevocation:
    """Token family revocation."""

    @pytest.mark.asyncio
    async def test_revoke_existing_family(self, mock_db_session):
        from ibreeze_backend.services.token_service import revoke_family

        family = MagicMock()
        family.status = "active"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = family
        mock_db_session.execute.return_value = mock_result

        result = await revoke_family(mock_db_session, "some-family-id")
        assert result is True
        assert family.status == "revoked"

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_family(self, mock_db_session):
        from ibreeze_backend.services.token_service import revoke_family

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await revoke_family(mock_db_session, "nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# Register, login, refresh, logout, change password (auth.service)
# ---------------------------------------------------------------------------

class TestRegister:
    """Registration flow."""

    @pytest.mark.asyncio
    async def test_register_success(self, mock_db_session):
        from ibreeze_backend.auth.service import register

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        user = await register(mock_db_session, "new@ibreeze.local", "password123")
        assert user.email == "new@ibreeze.local"
        assert user.user_type == "app_user"
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, mock_db_session):
        from ibreeze_backend.auth.service import register

        existing = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Email already registered"):
            await register(mock_db_session, "dup@ibreeze.local", "password123")


class TestLogin:
    """Login flow."""

    @pytest.mark.asyncio
    async def test_login_success(self, mock_db_session):
        from ibreeze_backend.auth.service import login
        from passlib.hash import argon2
        from ibreeze_backend.models.user import User

        user = MagicMock(spec=User)
        user.id = uuid.uuid4()
        user.email = "test@ibreeze.local"
        user.user_type = "admin"
        user.hashed_password = argon2.hash("correct_password")
        user.is_active = True
        user.must_change_password = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = mock_result

        result = await login(mock_db_session, "test@ibreeze.local", "correct_password", "admin")
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, mock_db_session):
        from ibreeze_backend.auth.service import login
        from passlib.hash import argon2

        user = MagicMock()
        user.hashed_password = argon2.hash("correct_password")
        user.is_active = True
        user.user_type = "admin"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Invalid credentials"):
            await login(mock_db_session, "test@ibreeze.local", "wrong_password", "admin")

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, mock_db_session):
        from ibreeze_backend.auth.service import login

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Invalid credentials"):
            await login(mock_db_session, "nobody@ibreeze.local", "password", "admin")

    @pytest.mark.asyncio
    async def test_login_disabled_account(self, mock_db_session):
        from ibreeze_backend.auth.service import login
        from passlib.hash import argon2

        user = MagicMock()
        user.hashed_password = argon2.hash("password")
        user.is_active = False
        user.user_type = "admin"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Account is disabled"):
            await login(mock_db_session, "test@ibreeze.local", "password", "admin")

    @pytest.mark.asyncio
    async def test_login_wrong_audience(self, mock_db_session):
        from ibreeze_backend.auth.service import login
        from passlib.hash import argon2

        user = MagicMock()
        user.hashed_password = argon2.hash("password")
        user.is_active = True
        user.user_type = "app_user"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Invalid credentials"):
            await login(mock_db_session, "test@ibreeze.local", "password", "admin")


class TestRefreshTokens:
    """Token refresh flow."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, mock_db_session):
        from ibreeze_backend.auth.service import refresh_tokens, create_refresh_token

        user_id = str(uuid.uuid4())
        family_id = str(uuid.uuid4())

        family = MagicMock()
        family.family_id = family_id
        family.status = "active"

        user = MagicMock()
        user.id = user_id
        user.must_change_password = False
        user.user_type = "admin"

        call_count = [0]

        def side_effect(stmt):
            nonlocal call_count
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = family
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = user
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db_session.execute.side_effect = side_effect

        token = create_refresh_token(user_id, family_id, "admin")
        result = await refresh_tokens(mock_db_session, token)
        assert "access_token" in result
        assert "refresh_token" in result

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, mock_db_session):
        from ibreeze_backend.auth.service import refresh_tokens

        with pytest.raises(ValueError, match="Invalid refresh token"):
            await refresh_tokens(mock_db_session, "invalid.token.here")

    @pytest.mark.asyncio
    async def test_refresh_token_reuse_detection(self, mock_db_session):
        from ibreeze_backend.auth.service import refresh_tokens, create_refresh_token

        user_id = str(uuid.uuid4())
        family_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        token = create_refresh_token(user_id, family_id, "admin")
        with pytest.raises(ValueError, match="Refresh token replay detected"):
            await refresh_tokens(mock_db_session, token)

    @pytest.mark.asyncio
    async def test_refresh_non_refresh_token_type(self, mock_db_session):
        from ibreeze_backend.auth.service import refresh_tokens, create_access_token

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        with pytest.raises(ValueError, match="Invalid refresh token"):
            await refresh_tokens(mock_db_session, token)


class TestLogout:
    """Logout flow."""

    @pytest.mark.asyncio
    async def test_logout_success(self, mock_db_session):
        from ibreeze_backend.auth.service import logout, create_access_token

        family = MagicMock()
        family.status = "active"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = family
        mock_db_session.execute.return_value = mock_result

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        result = await logout(mock_db_session, token)
        assert result is True
        assert family.status == "revoked"

    @pytest.mark.asyncio
    async def test_logout_invalid_token(self, mock_db_session):
        from ibreeze_backend.auth.service import logout

        result = await logout(mock_db_session, "invalid.token")
        assert result is False


class TestChangePassword:
    """Password change flow."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, mock_db_session):
        from ibreeze_backend.auth.service import change_password
        from passlib.hash import argon2

        user = MagicMock()
        user.id = uuid.uuid4()
        user.hashed_password = argon2.hash("old_password")
        user.user_type = "admin"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = mock_result

        result = await change_password(mock_db_session, user.id, "old_password", "new_password")
        assert "access_token" in result
        assert "refresh_token" in result
        assert user.must_change_password is False

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, mock_db_session):
        from ibreeze_backend.auth.service import change_password
        from passlib.hash import argon2

        user = MagicMock()
        user.id = uuid.uuid4()
        user.hashed_password = argon2.hash("real_old_password")
        user.user_type = "admin"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Invalid password"):
            await change_password(mock_db_session, user.id, "wrong_old", "new_password")

    @pytest.mark.asyncio
    async def test_change_password_nonexistent_user(self, mock_db_session):
        from ibreeze_backend.auth.service import change_password

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="User not found"):
            await change_password(mock_db_session, uuid.uuid4(), "old", "new")


# ---------------------------------------------------------------------------
# Audience separation & dependency injection
# ---------------------------------------------------------------------------

class TestAudienceSeparation:
    """Admin vs app audience separation."""

    def test_create_access_token_admin_audience(self):
        from ibreeze_backend.auth.service import create_access_token, verify_token

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "admin")
        payload = verify_token(token)
        assert payload["aud"] == "admin"

    def test_create_access_token_app_audience(self):
        from ibreeze_backend.auth.service import create_access_token, verify_token

        token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()), "app")
        payload = verify_token(token)
        assert payload["aud"] == "app"

    @pytest.mark.asyncio
    async def test_admin_auth_required(self, mock_db_session):
        from ibreeze_backend.dependencies import get_current_user
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.is_active = True
        mock_user.user_type = "app_user"

        with patch("ibreeze_backend.dependencies.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": str(uuid.uuid4()), "aud": "admin"}
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db_session.execute.return_value = mock_result

            creds = MagicMock()
            creds.credentials = "token"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=creds, db=mock_db_session)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_app_user_auth_required(self, mock_db_session):
        from ibreeze_backend.dependencies import get_current_user
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.is_active = True
        mock_user.user_type = "admin"

        with patch("ibreeze_backend.dependencies.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": str(uuid.uuid4()), "aud": "app"}
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db_session.execute.return_value = mock_result

            creds = MagicMock()
            creds.credentials = "token"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=creds, db=mock_db_session)
            assert exc_info.value.status_code == 401
