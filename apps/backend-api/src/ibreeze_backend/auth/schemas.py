"""Authentication request and response contracts from design section G.11."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    device_id: uuid.UUID


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=32, max_length=256)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserInfo(BaseModel):
    id: uuid.UUID
    user_type: Literal["admin", "app_user"]
    username: str | None = None
    email: str | None = None
    display_name: str
    masked_identifier: str
    status: Literal["active", "disabled"]


class SessionData(BaseModel):
    user: UserInfo
    access_token: str
    access_token_expires_in: int
    family_id: uuid.UUID
    pwd_change_required: bool = False
    refresh_token: str | None = None
    refresh_token_expires_in: int | None = None
    offline_session_ticket: str | None = None
    offline_session_ticket_expires_in: int | None = None


class RegisterData(BaseModel):
    user: UserInfo


class Meta(BaseModel):
    request_id: str


class RegisterResponse(BaseModel):
    data: RegisterData
    meta: Meta
    error: None = None


class SessionResponse(BaseModel):
    data: SessionData
    meta: Meta
    error: None = None


class AuthKeyInfo(BaseModel):
    kty: Literal["OKP"]
    crv: Literal["Ed25519"]
    kid: str
    use: Literal["sig"]
    alg: Literal["EdDSA"]
    x: str
    status: Literal["active", "retiring"]


class AuthKeysData(BaseModel):
    keys: list[AuthKeyInfo]
    issued_at: str
    expires_at: str
    signing_key_id: str
    signature_algorithm: Literal["Ed25519"]
    signature: str


class AuthKeysResponse(BaseModel):
    data: AuthKeysData
    meta: Meta
    error: None = None
