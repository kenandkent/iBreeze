from datetime import datetime, timedelta, timezone

import uuid
from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.models.admin import AdminSession, AdminUser


class AuthService:
    async def login(self, db: AsyncSession, username: str, password: str) -> dict:
        result = await db.execute(select(AdminUser).where(AdminUser.username == username))
        user = result.scalar_one_or_none()
        if not user or not bcrypt.verify(password, user.password_hash):
            raise ValueError("Invalid credentials")
        if user.status != "active":
            raise ValueError("Account disabled")

        user_data = {"user_id": user.user_id, "username": user.username, "role": user.role}
        access_token = create_access_token(user.user_id, user.role)
        refresh_token = create_refresh_token(user.user_id)

        session = AdminSession(
            session_id=str(uuid.uuid4()),
            user_id=user.user_id,
            refresh_token_hash=bcrypt.hash(refresh_token),
            expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        )
        db.add(session)
        await db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user_data,
        }

    async def refresh(self, db: AsyncSession, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise ValueError("Invalid token")
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        user_id = payload["sub"]
        result = await db.execute(select(AdminUser).where(AdminUser.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user or user.status != "active":
            raise ValueError("User not found or disabled")

        return {"access_token": create_access_token(user.user_id, user.role)}
