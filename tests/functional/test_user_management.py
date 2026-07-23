"""User management tests — CRUD, validation, role enforcement, auth dependency.

Covers design spec sections:
- G.12 User Management (admin/app_user types, protected admin, field whitelist)
- User creation, retrieval, update, deletion, pagination
- Password hashing with Argon2id
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestUserSchemas:
    """Pydantic schema validation for users."""

    def test_user_create_valid(self):
        from ibreeze_backend.schemas.user import UserCreate

        user = UserCreate(username="alice", email="alice@example.com", password="securepass1", role="admin")
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.role == "admin"

    def test_user_create_default_role(self):
        from ibreeze_backend.schemas.user import UserCreate

        user = UserCreate(username="bob", email="bob@example.com", password="securepass1")
        assert user.role == "viewer"

    def test_user_create_invalid_role_rejected(self):
        from ibreeze_backend.schemas.user import UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="a@b.com", password="securepass1", role="superadmin")

    def test_user_create_short_username_rejected(self):
        from ibreeze_backend.schemas.user import UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(username="ab", email="a@b.com", password="securepass1")

    def test_user_create_short_password_rejected(self):
        from ibreeze_backend.schemas.user import UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="a@b.com", password="short")

    def test_user_create_invalid_email_rejected(self):
        from ibreeze_backend.schemas.user import UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="not-an-email", password="securepass1")

    def test_user_update_partial(self):
        from ibreeze_backend.schemas.user import UserUpdate

        update = UserUpdate(email="new@example.com")
        assert update.email == "new@example.com"
        assert update.role is None
        assert update.is_active is None

    def test_user_update_invalid_role_rejected(self):
        from ibreeze_backend.schemas.user import UserUpdate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserUpdate(role="invalid_role")

    def test_user_response_from_attributes(self):
        from ibreeze_backend.schemas.user import UserResponse

        resp = UserResponse(
            id=str(uuid.uuid4()), username="alice", email="alice@example.com", role="admin", is_active=True
        )
        assert resp.is_active is True

    def test_user_list_response(self):
        from ibreeze_backend.schemas.user import UserListResponse, UserResponse

        users = [UserResponse(id=str(uuid.uuid4()), username="a", email="a@b.com", role="viewer", is_active=True)]
        resp = UserListResponse(users=users, total=1)
        assert len(resp.users) == 1
        assert resp.total == 1


# ---------------------------------------------------------------------------
# User service
# ---------------------------------------------------------------------------

class TestUserService:
    """User service CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_user(self, mock_db_session):
        from ibreeze_backend.services.user_service import create_user

        user = await create_user(mock_db_session, "alice", "alice@example.com", "password123", "admin")
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.role == "admin"
        assert user.hashed_password != "password123"
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_user_default_role(self, mock_db_session):
        from ibreeze_backend.services.user_service import create_user

        user = await create_user(mock_db_session, "bob", "bob@example.com", "password123")
        assert user.role == "viewer"

    @pytest.mark.asyncio
    async def test_create_user_password_is_argon2(self, mock_db_session):
        from ibreeze_backend.services.user_service import create_user
        from passlib.hash import argon2

        user = await create_user(mock_db_session, "alice", "a@b.com", "mypassword")
        assert argon2.verify("mypassword", user.hashed_password)

    @pytest.mark.asyncio
    async def test_get_user_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.services.user_service import get_user
        from ibreeze_backend.models.user import User

        user = User(username="alice", email="a@b.com", hashed_password="h", role="viewer", is_active=True)
        mock_db_session.execute.return_value = mock_scalar_result(user)

        result = await get_user(mock_db_session, uuid.uuid4())
        assert result == user

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.services.user_service import get_user

        mock_db_session.execute.return_value = mock_scalar_result(None)
        result = await get_user(mock_db_session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.services.user_service import get_user_by_username
        from ibreeze_backend.models.user import User

        user = User(username="alice", email="a@b.com", hashed_password="h", role="viewer", is_active=True)
        mock_db_session.execute.return_value = mock_scalar_result(user)

        result = await get_user_by_username(mock_db_session, "alice")
        assert result == user

    @pytest.mark.asyncio
    async def test_list_users(self, mock_db_session):
        from ibreeze_backend.services.user_service import list_users
        from ibreeze_backend.models.user import User

        users = [
            User(username="a", email="a@b.com", hashed_password="h", role="viewer", is_active=True),
            User(username="b", email="b@b.com", hashed_password="h", role="editor", is_active=True),
        ]

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = users

        mock_db_session.execute.side_effect = [count_result, list_result]

        result_users, total = await list_users(mock_db_session, skip=0, limit=10)
        assert total == 2
        assert len(result_users) == 2

    @pytest.mark.asyncio
    async def test_list_users_empty(self, mock_db_session):
        from ibreeze_backend.services.user_service import list_users

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [count_result, list_result]

        users, total = await list_users(mock_db_session)
        assert total == 0
        assert users == []

    @pytest.mark.asyncio
    async def test_update_user_email(self, mock_db_session):
        from ibreeze_backend.services.user_service import update_user
        from ibreeze_backend.models.user import User

        user = User(username="alice", email="old@b.com", hashed_password="h", role="viewer", is_active=True)
        updated = await update_user(mock_db_session, user, email="new@b.com")
        assert updated.email == "new@b.com"

    @pytest.mark.asyncio
    async def test_update_user_role(self, mock_db_session):
        from ibreeze_backend.services.user_service import update_user
        from ibreeze_backend.models.user import User

        user = User(username="alice", email="a@b.com", hashed_password="h", role="viewer", is_active=True)
        updated = await update_user(mock_db_session, user, role="admin")
        assert updated.role == "admin"

    @pytest.mark.asyncio
    async def test_update_user_deactivate(self, mock_db_session):
        from ibreeze_backend.services.user_service import update_user
        from ibreeze_backend.models.user import User

        user = User(username="alice", email="a@b.com", hashed_password="h", role="viewer", is_active=True)
        updated = await update_user(mock_db_session, user, is_active=False)
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_update_user_no_changes(self, mock_db_session):
        from ibreeze_backend.services.user_service import update_user
        from ibreeze_backend.models.user import User

        user = User(username="alice", email="a@b.com", hashed_password="h", role="viewer", is_active=True)
        original_email = user.email
        updated = await update_user(mock_db_session, user)
        assert updated.email == original_email

    @pytest.mark.asyncio
    async def test_delete_user(self, mock_db_session):
        from ibreeze_backend.services.user_service import delete_user
        from ibreeze_backend.models.user import User

        user = User(username="alice", email="a@b.com", hashed_password="h", role="viewer", is_active=True)
        await delete_user(mock_db_session, user)
        mock_db_session.delete.assert_awaited_once_with(user)
        mock_db_session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# Admin user management service
# ---------------------------------------------------------------------------

class TestAdminUserService:
    """Admin user management service CRUD."""

    @pytest.mark.asyncio
    async def test_create_admin_user(self, mock_db_session):
        from ibreeze_backend.users.service import create_admin_user
        from ibreeze_backend.models.user import User

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        user = await create_admin_user(mock_db_session, "new@test.com", "password123", "admin", admin)
        assert user.email == "new@test.com"
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_email(self, mock_db_session):
        from ibreeze_backend.users.service import create_admin_user
        from ibreeze_backend.models.user import User

        existing = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="Email already exists"):
            await create_admin_user(mock_db_session, "dup@test.com", "password123", "admin", admin)

    @pytest.mark.asyncio
    async def test_update_admin_user(self, mock_db_session):
        from ibreeze_backend.users.service import update_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="viewer", is_active=True)
        target.protected = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        updated = await update_admin_user(mock_db_session, target.id, email="new@test.com", role=None, is_active=None, admin_user=admin)
        assert updated.email == "new@test.com"

    @pytest.mark.asyncio
    async def test_protected_user_cannot_delete(self, mock_db_session):
        from ibreeze_backend.users.service import delete_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="admin", is_active=True)
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="Cannot delete protected user"):
            await delete_admin_user(mock_db_session, target.id, admin_user=admin)

    @pytest.mark.asyncio
    async def test_protected_user_cannot_change_email(self, mock_db_session):
        from ibreeze_backend.users.service import update_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="old@test.com", hashed_password="h", role="admin", is_active=True)
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="Cannot modify protected user"):
            await update_admin_user(mock_db_session, target.id, email="new@test.com", role=None, is_active=None, admin_user=admin)

    @pytest.mark.asyncio
    async def test_protected_user_cannot_change_role(self, mock_db_session):
        from ibreeze_backend.users.service import update_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="admin", is_active=True)
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="Cannot modify protected user"):
            await update_admin_user(mock_db_session, target.id, email=None, role="viewer", is_active=None, admin_user=admin)

    @pytest.mark.asyncio
    async def test_protected_user_cannot_change_active(self, mock_db_session):
        from ibreeze_backend.users.service import update_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="admin", is_active=True)
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="Cannot modify protected user"):
            await update_admin_user(mock_db_session, target.id, email=None, role=None, is_active=False, admin_user=admin)

    @pytest.mark.asyncio
    async def test_delete_admin_user(self, mock_db_session):
        from ibreeze_backend.users.service import delete_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="viewer", is_active=True)
        target.protected = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        await delete_admin_user(mock_db_session, target.id, admin_user=admin)
        mock_db_session.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, mock_db_session):
        from ibreeze_backend.users.service import delete_admin_user
        from ibreeze_backend.models.user import User

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="User not found"):
            await delete_admin_user(mock_db_session, uuid.uuid4(), admin_user=admin)

    @pytest.mark.asyncio
    async def test_reset_password(self, mock_db_session):
        from ibreeze_backend.users.service import reset_password
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="viewer", is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        user = await reset_password(mock_db_session, target.id, "new_password123", admin_user=admin)
        assert user.hashed_password != "h"
        assert user.hashed_password != "new_password123"

    @pytest.mark.asyncio
    async def test_revoke_sessions(self, mock_db_session):
        from ibreeze_backend.users.service import revoke_sessions
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="viewer", is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        result = await revoke_sessions(mock_db_session, target.id, admin_user=admin)
        assert result is True

    @pytest.mark.asyncio
    async def test_app_user_role_immutable(self, mock_db_session):
        from ibreeze_backend.users.service import update_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="viewer", is_active=True)
        target.user_type = "app_user"
        target.protected = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="Cannot change role for app_user"):
            await update_admin_user(mock_db_session, target.id, email=None, role="admin", is_active=None, admin_user=admin)

    @pytest.mark.asyncio
    async def test_app_user_active_immutable(self, mock_db_session):
        from ibreeze_backend.users.service import update_admin_user
        from ibreeze_backend.models.user import User

        target = User(username="u", email="u@test.com", hashed_password="h", role="viewer", is_active=True)
        target.user_type = "app_user"
        target.protected = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        with pytest.raises(ValueError, match="Cannot change is_active for app_user"):
            await update_admin_user(mock_db_session, target.id, email=None, role=None, is_active=False, admin_user=admin)

    @pytest.mark.asyncio
    async def test_pagination_cursor(self, mock_db_session):
        from ibreeze_backend.users.service import list_users_admin
        from ibreeze_backend.models.user import User
        import base64, json

        users = [
            User(username="a", email="a@b.com", hashed_password="h", role="viewer", is_active=True),
            User(username="b", email="b@b.com", hashed_password="h", role="viewer", is_active=True),
        ]

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = users

        mock_db_session.execute.side_effect = [count_result, list_result]

        result_users, next_cursor, total = await list_users_admin(mock_db_session, cursor=None, limit=50, user_type_filter=None)
        assert total == 2
        assert len(result_users) == 2
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_pagination_next_cursor(self, mock_db_session):
        from ibreeze_backend.users.service import list_users_admin
        from ibreeze_backend.models.user import User
        import base64, json
        from datetime import datetime, timezone

        users = [
            User(username="a", email="a@b.com", hashed_password="h", role="viewer", is_active=True),
            User(username="b", email="b@b.com", hashed_password="h", role="viewer", is_active=True),
        ]
        users[0].created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        users[0].id = uuid.uuid4()
        users[1].created_at = datetime(2025, 12, 1, tzinfo=timezone.utc)
        users[1].id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar.return_value = 3

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = users

        mock_db_session.execute.side_effect = [count_result, list_result]

        result_users, next_cursor, total = await list_users_admin(mock_db_session, cursor=None, limit=1, user_type_filter=None)
        assert total == 3
        assert len(result_users) == 1
        assert next_cursor is not None

    @pytest.mark.asyncio
    async def test_username_auto_generation(self, mock_db_session):
        from ibreeze_backend.users.service import create_admin_user
        from ibreeze_backend.models.user import User

        call_idx = [0]
        def side_effect(stmt):
            call_idx[0] += 1
            result = MagicMock()
            if call_idx[0] == 1:
                result.scalar_one_or_none.return_value = None
            elif call_idx[0] == 2:
                result.scalar_one_or_none.return_value = MagicMock()
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db_session.execute.side_effect = side_effect

        admin = User(username="admin", email="admin@test.com", hashed_password="h", role="admin", is_active=True)
        user = await create_admin_user(mock_db_session, "alice@test.com", "password123", "admin", admin)
        assert user.username is not None
        assert len(user.username) > 0


# ---------------------------------------------------------------------------
# User API router integration (with mocked auth)
# ---------------------------------------------------------------------------

class TestUserEndpoints:
    """User router endpoint logic."""

    @pytest.mark.asyncio
    async def test_create_user_endpoint(self, mock_db_session):
        from ibreeze_backend.routers.users import create_user_endpoint
        from ibreeze_backend.schemas.user import UserCreate

        with patch("ibreeze_backend.routers.users.create_user") as mock_create:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_user.username = "alice"
            mock_create.return_value = mock_user

            result = await create_user_endpoint(
                user_in=UserCreate(username="alice", email="alice@example.com", password="securepass1"),
                db=mock_db_session,
                _current_user=MagicMock(),
            )
            assert result.username == "alice"
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_users_endpoint(self, mock_db_session):
        from ibreeze_backend.routers.users import list_users_endpoint

        with patch("ibreeze_backend.routers.users.list_users") as mock_list:
            mock_list.return_value = ([], 0)
            result = await list_users_endpoint(db=mock_db_session, _current_user=MagicMock())
            assert result == {"users": [], "total": 0}

    @pytest.mark.asyncio
    async def test_get_user_endpoint_found(self, mock_db_session):
        from ibreeze_backend.routers.users import get_user_endpoint

        with patch("ibreeze_backend.routers.users.get_user") as mock_get:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_get.return_value = mock_user
            result = await get_user_endpoint(user_id=uuid.uuid4(), db=mock_db_session, _current_user=MagicMock())
            assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_endpoint_not_found(self, mock_db_session):
        from ibreeze_backend.routers.users import get_user_endpoint
        from fastapi import HTTPException

        with patch("ibreeze_backend.routers.users.get_user") as mock_get:
            mock_get.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await get_user_endpoint(user_id=uuid.uuid4(), db=mock_db_session, _current_user=MagicMock())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user_endpoint(self, mock_db_session):
        from ibreeze_backend.routers.users import delete_user_endpoint

        with (
            patch("ibreeze_backend.routers.users.get_user") as mock_get,
            patch("ibreeze_backend.routers.users.delete_user") as mock_delete,
        ):
            mock_get.return_value = MagicMock()
            await delete_user_endpoint(user_id=uuid.uuid4(), db=mock_db_session, _current_user=MagicMock())
            mock_delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

class TestAuthDependency:
    """get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, mock_db_session):
        from ibreeze_backend.dependencies import get_current_user

        mock_user = MagicMock()
        mock_user.is_active = True

        with patch("ibreeze_backend.dependencies.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": str(uuid.uuid4())}
            with patch("ibreeze_backend.dependencies.select") as mock_select:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_user
                mock_db_session.execute.return_value = mock_result

                creds = MagicMock()
                creds.credentials = "valid.token"
                user = await get_current_user(credentials=creds, db=mock_db_session)
                assert user == mock_user

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self, mock_db_session):
        from ibreeze_backend.dependencies import get_current_user
        from fastapi import HTTPException

        with patch("ibreeze_backend.dependencies.verify_token") as mock_verify:
            mock_verify.return_value = None
            creds = MagicMock()
            creds.credentials = "bad.token"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=creds, db=mock_db_session)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_raises_401(self, mock_db_session):
        from ibreeze_backend.dependencies import get_current_user
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.is_active = False

        with patch("ibreeze_backend.dependencies.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": str(uuid.uuid4())}
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db_session.execute.return_value = mock_result

            creds = MagicMock()
            creds.credentials = "valid.token"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=creds, db=mock_db_session)
            assert exc_info.value.status_code == 401
