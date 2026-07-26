"""RFC 9457 Problem Details error handling with reference_id and redaction."""

import logging
import re
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("ibreeze.errors")

SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?\S+['\"]?"), r"\1: ***"),
    (re.compile(r"(?i)(token|jwt|bearer)\s+[\w.-]+\b"), r"\1 ***"),
    (re.compile(r"(?i)(secret|api[_-]?key|apikey)\s*[:=]\s*['\"]?\S+['\"]?"), r"\1: ***"),
    (re.compile(r"(?i)(authorization:\s*)(bearer\s+)?[\w.-]+"), r"\1***"),
    (re.compile(r"(?i)(connection\s+(string|uri)|connstr)\s*[:=].*?(?=[;\s]|$)"), r"\1: ***"),
    (re.compile(r"(/api/v\d+/[\w/-]+)"), r"[PATH_REDACTED]"),
    (re.compile(r"(?i)(SELECT|INSERT|UPDATE|DELETE)\s+.*?(?:;|\Z)"), r"[SQL_REDACTED]"),
]


def redact_sensitive(value: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in data.items():
        if isinstance(val, str):
            result[key] = redact_sensitive(val)
        elif isinstance(val, dict):
            result[key] = redact_dict(val)
        elif isinstance(val, list):
            result[key] = [redact_sensitive(str(v)) if isinstance(v, str) else v for v in val]
        else:
            result[key] = val
    return result


class ProblemDetailError(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        code: str,
        detail: str = "",
        type: str = "about:blank",
        reference_id: str | None = None,
        field_errors: dict[str, list[str]] | None = None,
    ):
        self.status = status
        self.title = title
        self.code = code
        self.detail = detail
        self.type = type
        self.reference_id = reference_id
        self.field_errors = field_errors
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": self.code,
            "message": self.detail or self.title,
        }
        if self.reference_id:
            body["reference_id"] = self.reference_id
        if self.field_errors:
            body["field_errors"] = self.field_errors
        return body


async def problem_detail_handler(request: Request, exc: ProblemDetailError) -> JSONResponse:
    reference_id = exc.reference_id or getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    body = exc.to_dict()
    body["reference_id"] = reference_id
    logger.warning(
        "problem_detail",
        extra={"status": exc.status, "code": exc.code, "reference_id": reference_id, "detail": exc.detail},
    )
    return JSONResponse(
        status_code=exc.status,
        content=body,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    reference_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    logger.exception(
        "unhandled_exception",
        extra={"reference_id": reference_id, "path": str(request.url.path)},
    )
    err_msg = str(exc)
    redacted = redact_sensitive(err_msg)
    if redacted != err_msg:
        logger.info("redacted_sensitive_data", extra={"reference_id": reference_id})
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "reference_id": reference_id,
        },
    )


def raise_problem(
    status_code: int,
    code: str,
    detail: str,
    reference_id: str | None = None,
    field_errors: dict[str, list[str]] | None = None,
) -> None:
    title = _STATUS_TITLES.get(status_code, "Error")
    raise ProblemDetailError(
        status=status_code,
        title=title,
        code=code,
        detail=detail,
        reference_id=reference_id,
        field_errors=field_errors,
    )


_STATUS_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    428: "Precondition Required",
    429: "Too Many Requests",
    500: "Internal Server Error",
}
