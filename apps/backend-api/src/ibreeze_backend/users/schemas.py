"""Admin user management request and response contracts."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class UserAdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_type: Literal["admin", "app_user"]
    username: str | None = Field(default=None, min_length=1, max_length=64)
    email: EmailStr | None = None
    display_name: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_identity_fields(self) -> Self:
        if self.user_type == "admin":
            if self.username is None or self.email is not None:
                raise ValueError("admin requires username and forbids email")
        elif self.email is None or self.username is not None:
            raise ValueError("app_user requires email and forbids username")
        return self


class UserAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=64)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=320)
    status: Literal["active", "disabled"] | None = None


class UserAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_type: Literal["admin", "app_user"]
    username: str | None
    email: str | None
    display_name: str
    status: Literal["active", "disabled"]
    protected: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime
    version: int


class UserAdminListResponse(BaseModel):
    users: list[UserAdminResponse]
    next_cursor: str | None = None
    total: int


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=8, max_length=128)
