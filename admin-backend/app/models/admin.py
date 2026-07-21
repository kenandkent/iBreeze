from sqlalchemy import Column, String, func

from app.models.base import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    user_id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, server_default="viewer")
    status = Column(String, nullable=False, server_default="active")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    session_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    refresh_token_hash = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)
    created_at = Column(String, server_default=func.datetime("now"))
