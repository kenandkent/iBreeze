"""User management tests — CRUD, validation, role enforcement, auth dependency.

Covers design spec sections:
- G.12 User Management (admin/app_user types, protected admin, field whitelist)
- User creation, retrieval, update, deletion, pagination
- Password hashing with Argon2id
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestUserSchemas:
    """Pydantic schema validation for users."""

    def test_user_create_valid(self):
        from ibreeze_backend.users.schemas import UserAdminCreate as UserCreate

        user = UserCreate(
            user_type="admin",
            username="alice",
            email=None,
            display_name="Alice",
            password="securepass1",
        )
        assert user.username == "alice"
        assert user.user_type == "admin"

    def test_user_create_invalid_role_rejected(self):
        from ibreeze_backend.users.schemas import UserAdminCreate as UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_type="superadmin",
                username="alice",
                email=None,
                display_name="Alice",
                password="securepass1",
            )

    def test_user_create_empty_username_rejected(self):
        from ibreeze_backend.users.schemas import UserAdminCreate as UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_type="admin",
                username="",
                email=None,
                display_name="Alice",
                password="securepass1",
            )

    def test_user_create_short_password_rejected(self):
        from ibreeze_backend.users.schemas import UserAdminCreate as UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_type="admin",
                username="alice",
                email=None,
                display_name="Alice",
                password="short",
            )

    def test_user_create_invalid_email_rejected(self):
        from ibreeze_backend.users.schemas import UserAdminCreate as UserCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_type="admin",
                username="alice",
                email="not-an-email",
                display_name="Alice",
                password="securepass1",
            )

    def test_user_update_partial(self):
        from ibreeze_backend.users.schemas import UserAdminUpdate as UserUpdate

        update = UserUpdate(email="new@example.com")
        assert update.email == "new@example.com"
        assert update.username is None
        assert update.display_name is None
        assert update.status is None

    def test_user_update_invalid_role_rejected(self):
        from ibreeze_backend.users.schemas import UserAdminUpdate as UserUpdate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserUpdate(role="invalid_role")

    def test_user_response_from_attributes(self):
        from datetime import UTC, datetime

        from ibreeze_backend.users.schemas import UserAdminResponse as UserResponse

        resp = UserResponse(
            id=uuid.uuid4(),
            user_type="admin",
            username="alice",
            email=None,
            display_name="Alice",
            status="active",
            protected=False,
            must_change_password=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            version=1,
        )
        assert resp.status == "active"

    def test_user_list_response(self):
        from datetime import UTC, datetime

        from ibreeze_backend.users.schemas import (
            UserAdminListResponse as UserListResponse,
            UserAdminResponse as UserResponse,
        )

        users = [
            UserResponse(
                id=uuid.uuid4(),
                user_type="app_user",
                username=None,
                email="a@b.com",
                display_name="A",
                status="active",
                protected=False,
                must_change_password=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                version=1,
            )
        ]
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
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import create_admin_user as create_user

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        user = await create_user(
            mock_db_session,
            user_type="admin",
            username="alice",
            email=None,
            display_name="Alice",
            password="password123",
            admin_user=admin,
        )
        assert user.username == "alice"
        assert user.user_type == "admin"
        assert user.password_hash != "password123"
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_user_app_type(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import create_admin_user as create_user

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        user = await create_user(
            mock_db_session,
            user_type="app_user",
            username=None,
            email="bob@example.com",
            display_name="Bob",
            password="password123",
            admin_user=admin,
        )
        assert user.email == "bob@example.com"
        assert user.user_type == "app_user"

    @pytest.mark.asyncio
    async def test_create_user_password_is_argon2(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import create_admin_user as create_user
        from passlib.hash import argon2

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        user = await create_user(
            mock_db_session,
            user_type="admin",
            username="alice",
            email=None,
            display_name="Alice",
            password="mypassword",
            admin_user=admin,
        )
        assert argon2.verify("mypassword", user.password_hash)

    @pytest.mark.asyncio
    async def test_list_users(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import list_users_admin as list_users

        users = [
            User(
                user_type="app_user",
                username=None,
                email="a@b.com",
                password_hash="h",
                display_name="A",
                status="active",
            ),
            User(
                user_type="app_user",
                username=None,
                email="b@b.com",
                password_hash="h",
                display_name="B",
                status="active",
            ),
        ]

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = users

        mock_db_session.execute.side_effect = [count_result, list_result]

        result_users, next_cursor, total = await list_users(
            mock_db_session, cursor=None, limit=10, user_type_filter=None
        )
        assert total == 2
        assert len(result_users) == 2

    @pytest.mark.asyncio
    async def test_list_users_empty(self, mock_db_session):
        from ibreeze_backend.users.service import list_users_admin as list_users

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [count_result, list_result]

        users, next_cursor, total = await list_users(
            mock_db_session, cursor=None, limit=10, user_type_filter=None
        )
        assert total == 0
        assert users == []

    @pytest.mark.asyncio
    async def test_update_user_email(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user as update_user

        target = User(
            user_type="app_user",
            username=None,
            email="old@b.com",
            password_hash="h",
            display_name="Old",
            status="active",
            version=1,
        )
        target.protected = False

        user_lookup = MagicMock()
        user_lookup.scalar_one_or_none.return_value = target
        conflict_check = MagicMock()
        conflict_check.scalar_one_or_none.return_value = None
        mock_db_session.execute.side_effect = [user_lookup, conflict_check]

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        updated = await update_user(
            mock_db_session,
            user_id=target.id,
            username=None,
            email="new@b.com",
            display_name=None,
            status=None,
            admin_user=admin,
        )
        assert updated.email == "new@b.com"

    @pytest.mark.asyncio
    async def test_update_user_display_name(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user as update_user

        target = User(
            user_type="app_user",
            username=None,
            email="a@b.com",
            password_hash="h",
            display_name="Old Name",
            status="active",
            version=1,
        )
        target.protected = False

        user_lookup = MagicMock()
        user_lookup.scalar_one_or_none.return_value = target
        conflict_check = MagicMock()
        conflict_check.scalar_one_or_none.return_value = None
        mock_db_session.execute.side_effect = [user_lookup, conflict_check]

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        updated = await update_user(
            mock_db_session,
            user_id=target.id,
            username=None,
            email=None,
            display_name="New Name",
            status=None,
            admin_user=admin,
        )
        assert updated.display_name == "New Name"

    @pytest.mark.asyncio
    async def test_update_user_deactivate(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user as update_user

        target = User(
            user_type="app_user",
            username=None,
            email="a@b.com",
            password_hash="h",
            display_name="A",
            status="active",
            version=1,
        )
        target.protected = False

        user_lookup = MagicMock()
        user_lookup.scalar_one_or_none.return_value = target
        conflict_check = MagicMock()
        conflict_check.scalar_one_or_none.return_value = None
        revoke_result = MagicMock()
        revoke_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [
            user_lookup,
            conflict_check,
            revoke_result,
        ]

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        updated = await update_user(
            mock_db_session,
            user_id=target.id,
            username=None,
            email=None,
            display_name=None,
            status="disabled",
            admin_user=admin,
        )
        assert updated.status == "disabled"

    @pytest.mark.asyncio
    async def test_update_user_no_changes(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user as update_user

        target = User(
            user_type="app_user",
            username=None,
            email="a@b.com",
            password_hash="h",
            display_name="A",
            status="active",
            version=1,
        )
        target.protected = False

        user_lookup = MagicMock()
        user_lookup.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = user_lookup

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        original_email = target.email
        updated = await update_user(
            mock_db_session,
            user_id=target.id,
            username=None,
            email=None,
            display_name=None,
            status=None,
            admin_user=admin,
        )
        assert updated.email == original_email

    @pytest.mark.asyncio
    async def test_delete_user(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import delete_admin_user as delete_user

        target = User(
            user_type="app_user",
            username=None,
            email="a@b.com",
            password_hash="h",
            display_name="A",
            status="active",
            version=1,
        )
        target.protected = False

        user_lookup = MagicMock()
        user_lookup.scalar_one_or_none.return_value = target
        revoke_result = MagicMock()
        revoke_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [user_lookup, revoke_result]

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        await delete_user(mock_db_session, user_id=target.id, admin_user=admin)
        mock_db_session.delete.assert_awaited_once_with(target)
        mock_db_session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# Admin user management service
# ---------------------------------------------------------------------------


class TestAdminUserService:
    """Admin user management service CRUD."""

    @pytest.mark.asyncio
    async def test_create_admin_user(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import create_admin_user

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        user = await create_admin_user(
            mock_db_session,
            user_type="app_user",
            username=None,
            email="new@test.com",
            display_name="New User",
            password="password123",
            admin_user=admin,
        )
        assert user.email == "new@test.com"
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_email(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import create_admin_user

        existing = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="Email already exists"):
            await create_admin_user(
                mock_db_session,
                user_type="app_user",
                username=None,
                email="dup@test.com",
                display_name="Dup User",
                password="password123",
                admin_user=admin,
            )

    @pytest.mark.asyncio
    async def test_update_admin_user(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user

        target = User(
            user_type="app_user",
            username=None,
            email="u@test.com",
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = False
        user_lookup = MagicMock()
        user_lookup.scalar_one_or_none.return_value = target
        conflict_check = MagicMock()
        conflict_check.scalar_one_or_none.return_value = None
        mock_db_session.execute.side_effect = [user_lookup, conflict_check]

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        updated = await update_admin_user(
            mock_db_session,
            user_id=target.id,
            username=None,
            email="new@test.com",
            display_name=None,
            status=None,
            admin_user=admin,
        )
        assert updated.email == "new@test.com"

    @pytest.mark.asyncio
    async def test_protected_user_cannot_delete(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import delete_admin_user

        target = User(
            user_type="admin",
            username="u",
            email=None,
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="Cannot delete protected user"):
            await delete_admin_user(
                mock_db_session, user_id=target.id, admin_user=admin
            )

    @pytest.mark.asyncio
    async def test_protected_user_cannot_change_email(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user

        target = User(
            user_type="admin",
            username="u",
            email=None,
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="Cannot modify protected user"):
            await update_admin_user(
                mock_db_session,
                user_id=target.id,
                username=None,
                email="new@test.com",
                display_name=None,
                status=None,
                admin_user=admin,
            )

    @pytest.mark.asyncio
    async def test_protected_user_cannot_change_status(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user

        target = User(
            user_type="admin",
            username="u",
            email=None,
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="Cannot modify protected user"):
            await update_admin_user(
                mock_db_session,
                user_id=target.id,
                username=None,
                email=None,
                display_name=None,
                status="disabled",
                admin_user=admin,
            )

    @pytest.mark.asyncio
    async def test_protected_user_cannot_change_username(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user

        target = User(
            user_type="admin",
            username="u",
            email=None,
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="Cannot modify protected user"):
            await update_admin_user(
                mock_db_session,
                user_id=target.id,
                username="new_name",
                email=None,
                display_name=None,
                status=None,
                admin_user=admin,
            )

    @pytest.mark.asyncio
    async def test_delete_admin_user(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import delete_admin_user

        target = User(
            user_type="app_user",
            username=None,
            email="u@test.com",
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        await delete_admin_user(mock_db_session, user_id=target.id, admin_user=admin)
        mock_db_session.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import delete_admin_user

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="User not found"):
            await delete_admin_user(
                mock_db_session, user_id=uuid.uuid4(), admin_user=admin
            )

    @pytest.mark.asyncio
    async def test_reset_password(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import reset_password

        target = User(
            user_type="app_user",
            username=None,
            email="u@test.com",
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        user = await reset_password(
            mock_db_session,
            user_id=target.id,
            new_password="new_password123",
            admin_user=admin,
        )
        assert user.password_hash != "h"
        assert user.password_hash != "new_password123"

    @pytest.mark.asyncio
    async def test_revoke_sessions(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import revoke_sessions

        target = User(
            user_type="app_user",
            username=None,
            email="u@test.com",
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        result = await revoke_sessions(
            mock_db_session, user_id=target.id, admin_user=admin
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_app_user_cannot_set_username(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user

        target = User(
            user_type="app_user",
            username=None,
            email="u@test.com",
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="Cannot set username for app_user"):
            await update_admin_user(
                mock_db_session,
                user_id=target.id,
                username="new_name",
                email=None,
                display_name=None,
                status=None,
                admin_user=admin,
            )

    @pytest.mark.asyncio
    async def test_admin_cannot_set_email(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import update_admin_user

        target = User(
            user_type="admin",
            username="u",
            email=None,
            password_hash="h",
            display_name="U",
            status="active",
            version=1,
        )
        target.protected = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = mock_result

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        with pytest.raises(ValueError, match="Cannot set email for admin user"):
            await update_admin_user(
                mock_db_session,
                user_id=target.id,
                username=None,
                email="new@test.com",
                display_name=None,
                status=None,
                admin_user=admin,
            )

    @pytest.mark.asyncio
    async def test_pagination_cursor(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import list_users_admin

        users = [
            User(
                user_type="app_user",
                username=None,
                email="a@b.com",
                password_hash="h",
                display_name="A",
                status="active",
            ),
            User(
                user_type="app_user",
                username=None,
                email="b@b.com",
                password_hash="h",
                display_name="B",
                status="active",
            ),
        ]

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = users

        mock_db_session.execute.side_effect = [count_result, list_result]

        result_users, next_cursor, total = await list_users_admin(
            mock_db_session, cursor=None, limit=50, user_type_filter=None
        )
        assert total == 2
        assert len(result_users) == 2
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_pagination_next_cursor(self, mock_db_session):
        from datetime import datetime, timezone

        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import list_users_admin

        users = [
            User(
                user_type="app_user",
                username=None,
                email="a@b.com",
                password_hash="h",
                display_name="A",
                status="active",
            ),
            User(
                user_type="app_user",
                username=None,
                email="b@b.com",
                password_hash="h",
                display_name="B",
                status="active",
            ),
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

        result_users, next_cursor, total = await list_users_admin(
            mock_db_session, cursor=None, limit=1, user_type_filter=None
        )
        assert total == 3
        assert len(result_users) == 1
        assert next_cursor is not None

    @pytest.mark.asyncio
    async def test_username_auto_generation(self, mock_db_session):
        from ibreeze_backend.models.user import User
        from ibreeze_backend.users.service import create_admin_user

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

        admin = User(
            user_type="admin",
            username="admin",
            email=None,
            display_name="Admin",
            password_hash="h",
            status="active",
            version=1,
        )
        user = await create_admin_user(
            mock_db_session,
            user_type="app_user",
            username=None,
            email="alice@test.com",
            display_name="Alice",
            password="password123",
            admin_user=admin,
        )
        assert user.email is not None


# ---------------------------------------------------------------------------
# User API router integration (with mocked auth)
# ---------------------------------------------------------------------------


class TestUserEndpoints:
    """User router endpoint logic."""

    @pytest.mark.asyncio
    async def test_create_user_endpoint(self, mock_db_session):
        from ibreeze_backend.users.router import create_user_endpoint
        from ibreeze_backend.users.schemas import UserAdminCreate as UserCreate

        with patch("ibreeze_backend.users.router.create_admin_user") as mock_create:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_user.username = "alice"
            mock_create.return_value = mock_user

            result = await create_user_endpoint(
                user_in=UserCreate(
                    user_type="admin",
                    username="alice",
                    email=None,
                    display_name="Alice",
                    password="securepass1",
                ),
                db=mock_db_session,
                current_user=MagicMock(),
            )
            assert result.username == "alice"
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_users_endpoint(self, mock_db_session):
        from ibreeze_backend.users.router import list_users_endpoint

        with patch("ibreeze_backend.users.router.list_users_admin") as mock_list:
            mock_list.return_value = ([], None, 0)
            result = await list_users_endpoint(
                db=mock_db_session, current_user=MagicMock()
            )
            assert result == {"users": [], "next_cursor": None, "total": 0}

    @pytest.mark.asyncio
    async def test_get_user_endpoint_found(self, mock_db_session):
        from ibreeze_backend.users.router import get_user_endpoint

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db_session.execute.return_value = mock_result

        result = await get_user_endpoint(
            user_id=uuid.uuid4(), db=mock_db_session, current_user=MagicMock()
        )
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_endpoint_not_found(self, mock_db_session):
        from fastapi import HTTPException

        from ibreeze_backend.users.router import get_user_endpoint

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_user_endpoint(
                user_id=uuid.uuid4(), db=mock_db_session, current_user=MagicMock()
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user_endpoint(self, mock_db_session):
        from ibreeze_backend.users.router import delete_user_endpoint

        with patch("ibreeze_backend.users.router.delete_admin_user") as mock_delete:
            await delete_user_endpoint(
                user_id=uuid.uuid4(), db=mock_db_session, current_user=MagicMock()
            )
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
        mock_user.status = "active"
        mock_user.user_type = "admin"
        mock_user.must_change_password = False

        mock_request = MagicMock()
        mock_request.url.path = "/admin/api/v1/users"
        mock_request.method = "GET"

        with patch("ibreeze_backend.dependencies.verify_access_token") as mock_verify:
            mock_verify.return_value = {"sub": str(uuid.uuid4())}
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db_session.execute.return_value = mock_result

            creds = MagicMock()
            creds.credentials = "valid.token"
            user = await get_current_user(
                request=mock_request, credentials=creds, db=mock_db_session
            )
            assert user == mock_user

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self, mock_db_session):
        from fastapi import HTTPException

        from ibreeze_backend.dependencies import get_current_user

        mock_request = MagicMock()
        mock_request.url.path = "/admin/api/v1/users"

        with patch("ibreeze_backend.dependencies.verify_access_token") as mock_verify:
            mock_verify.return_value = None
            creds = MagicMock()
            creds.credentials = "bad.token"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=mock_request, credentials=creds, db=mock_db_session
                )
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_raises_401(self, mock_db_session):
        from fastapi import HTTPException

        from ibreeze_backend.dependencies import get_current_user

        mock_user = MagicMock()
        mock_user.status = "disabled"

        mock_request = MagicMock()
        mock_request.url.path = "/admin/api/v1/users"

        with patch("ibreeze_backend.dependencies.verify_access_token") as mock_verify:
            mock_verify.return_value = {"sub": str(uuid.uuid4())}
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db_session.execute.return_value = mock_result

            creds = MagicMock()
            creds.credentials = "valid.token"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=mock_request, credentials=creds, db=mock_db_session
                )
            assert exc_info.value.status_code == 401
