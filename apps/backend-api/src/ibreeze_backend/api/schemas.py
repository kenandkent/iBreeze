"""Response envelope schemas."""
import uuid
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    request_id: str


class ErrorBody(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str = ""
    request_id: str | None = None
    field_errors: dict[str, list[str]] | None = None


class EnvelopeResponse(BaseModel, Generic[T]):
    data: T | None = None
    meta: Meta | None = None
    error: ErrorBody | None = None


def success_response(
    data: Any, request_id: str | None = None
) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {"request_id": request_id} if request_id else None,
        "error": None,
    }


def error_response(
    error: ErrorBody, request_id: str | None = None
) -> dict[str, Any]:
    if request_id:
        error.request_id = request_id
    return {
        "data": None,
        "meta": {"request_id": request_id} if request_id else None,
        "error": error.model_dump(exclude_none=True),
    }
