"""User management schemas."""
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(default="viewer", pattern="^(admin|editor|viewer)$")


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: str | None = Field(default=None, pattern="^(admin|editor|viewer)$")
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
