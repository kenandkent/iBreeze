"""RFC 9457 Problem Details error handling."""

import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ProblemDetailError(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        code: str,
        detail: str = "",
        type: str = "about:blank",
        request_id: str | None = None,
        field_errors: dict[str, list[str]] | None = None,
    ):
        self.status = status
        self.title = title
        self.code = code
        self.detail = detail
        self.type = type
        self.request_id = request_id
        self.field_errors = field_errors
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
        }
        if self.request_id:
            body["request_id"] = self.request_id
        if self.field_errors:
            body["field_errors"] = self.field_errors
        return body


async def problem_detail_handler(request: Request, exc: ProblemDetailError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "code": "INTERNAL_ERROR",
            "detail": "An unexpected error occurred.",
            "request_id": request_id,
        },
    )


def raise_problem(
    status_code: int,
    code: str,
    detail: str,
    request_id: str | None = None,
    field_errors: dict[str, list[str]] | None = None,
) -> None:
    title = _STATUS_TITLES.get(status_code, "Error")
    raise ProblemDetailError(
        status=status_code,
        title=title,
        code=code,
        detail=detail,
        request_id=request_id,
        field_errors=field_errors,
    )


_STATUS_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
}
