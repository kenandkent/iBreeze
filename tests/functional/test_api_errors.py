"""API error handling tests — ProblemDetail format, validation, generic handler.

Covers design spec sections:
- G.14 Error handling (RFC 9457 Problem Details)
"""
import uuid
from unittest.mock import MagicMock

import pytest


class TestProblemDetail:
    """ProblemDetail error response format."""

    def test_problem_detail_format(self):
        from ibreeze_backend.api.errors import ProblemDetail

        exc = ProblemDetail(
            status=400,
            title="Bad Request",
            code="VALIDATION_ERROR",
            detail="Email is required",
            request_id=str(uuid.uuid4()),
        )
        body = exc.to_dict()
        assert body["type"] == "about:blank"
        assert body["title"] == "Bad Request"
        assert body["status"] == 400
        assert body["code"] == "VALIDATION_ERROR"
        assert body["detail"] == "Email is required"
        assert "request_id" in body

    def test_problem_detail_with_field_errors(self):
        from ibreeze_backend.api.errors import ProblemDetail

        exc = ProblemDetail(
            status=422,
            title="Unprocessable Entity",
            code="VALIDATION_ERROR",
            detail="Invalid input",
            field_errors={"email": ["Invalid email format"]},
        )
        body = exc.to_dict()
        assert "field_errors" in body
        assert body["field_errors"]["email"] == ["Invalid email format"]

    def test_validation_error(self):
        from ibreeze_backend.api.errors import ProblemDetail, raise_problem

        with pytest.raises(ProblemDetail) as exc_info:
            raise_problem(400, "VALIDATION_ERROR", "Invalid input")
        assert exc_info.value.status == 400

    def test_not_found_error(self):
        from ibreeze_backend.api.errors import ProblemDetail, raise_problem

        with pytest.raises(ProblemDetail) as exc_info:
            raise_problem(404, "NOT_FOUND", "Resource not found")
        assert exc_info.value.status == 404

    def test_generic_exception_handler(self):
        from ibreeze_backend.api.errors import generic_exception_handler

        request = MagicMock()
        request.state.request_id = str(uuid.uuid4())
        exc = Exception("something broke")

        import asyncio
        response = asyncio.run(
            generic_exception_handler(request, exc)
        )
        assert response.status_code == 500
        assert response.body is not None
