"""Admin user management schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserAdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    user_type: str = Field(..., pattern="^(admin|app_user)$")


class UserAdminUpdate(BaseModel):
    email: EmailStr | None = None
    role: str | None = Field(default=None, pattern="^(admin|editor|viewer)$")
    is_active: bool | None = None


class UserAdminResponse(BaseModel):
    id: uuid.UUID
    email: str
    user_type: str
    role: str
    is_active: bool
    protected: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserAdminListResponse(BaseModel):
    users: list[UserAdminResponse]
    next_cursor: str | None = None
    total: int


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8)
