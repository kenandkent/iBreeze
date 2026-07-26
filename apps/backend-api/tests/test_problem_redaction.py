"""Test that error responses don't leak sensitive data and reference_id is present."""

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from ibreeze_backend.api.errors import (
    ProblemDetailError,
    generic_exception_handler,
    problem_detail_handler,
    redact_sensitive,
)


@pytest.mark.asyncio
async def test_problem_detail_has_code_and_message():
    exc = ProblemDetailError(status=404, title="Not Found", code="RESOURCE_NOT_FOUND", detail="Resource not found")
    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": [], "query_string": b""})
    request.state.request_id = "abc123"
    response: JSONResponse = await problem_detail_handler(request, exc)
    body = response.body.decode()
    assert '"code"' in body
    assert '"message"' in body
    assert '"reference_id"' in body
    assert '"type"' not in body
    assert '"title"' not in body


@pytest.mark.asyncio
async def test_generic_exception_returns_internal_error_with_reference_id():
    exc = ValueError("something broke")
    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": [], "query_string": b""})
    request.state.request_id = "ref123"
    response: JSONResponse = await generic_exception_handler(request, exc)
    body = response.body.decode()
    assert '"INTERNAL_ERROR"' in body
    assert '"message"' in body
    assert '"reference_id"' in body
    assert '"ref123"' in body


@pytest.mark.asyncio
async def test_generic_exception_does_not_leak_stack_trace():
    exc = RuntimeError("sensitive internal detail")
    request = Request({"type": "http", "method": "GET", "path": "/test", "headers": [], "query_string": b""})
    request.state.request_id = "ref456"
    response: JSONResponse = await generic_exception_handler(request, exc)
    body = response.body.decode()
    assert "sensitive internal detail" not in body
    assert "Traceback" not in body
    assert "RuntimeError" not in body


class TestRedactSensitive:
    def test_redacts_password(self):
        assert redact_sensitive("password=super_secret") == "password: ***"

    def test_redacts_token(self):
        assert redact_sensitive("Bearer eyJhbGciOiJIUzI1NiJ9.token") == "Bearer ***"

    def test_redacts_api_key(self):
        assert "***" in redact_sensitive("api_key=sk-1234567890abcdef")

    def test_redacts_sql(self):
        assert "[SQL_REDACTED]" in redact_sensitive("SELECT * FROM users WHERE password = 'secret'")

    def test_redacts_paths(self):
        assert "[PATH_REDACTED]" in redact_sensitive("Failed at /api/v1/admin/users")

    def test_no_false_positive_on_safe_string(self):
        safe = "Hello world, this is a normal message."
        assert redact_sensitive(safe) == safe
