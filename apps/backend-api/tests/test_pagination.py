"""Tests for cursor-based pagination helpers."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ibreeze_backend.api.pagination import (
    CursorParams,
    decode_cursor,
    encode_cursor,
)


class TestCursorParams:
    def test_defaults(self):
        params = CursorParams()
        assert params.cursor is None
        assert params.limit == 50

    def test_with_cursor(self):
        params = CursorParams(cursor="abc123")
        assert params.cursor == "abc123"
        assert params.limit == 50

    def test_custom_limit(self):
        params = CursorParams(limit=10)
        assert params.limit == 10

    def test_limit_min_boundary(self):
        params = CursorParams(limit=1)
        assert params.limit == 1

    def test_limit_max_boundary(self):
        params = CursorParams(limit=200)
        assert params.limit == 200

    def test_limit_below_min(self):
        with pytest.raises(ValidationError):
            CursorParams(limit=0)

    def test_limit_above_max(self):
        with pytest.raises(ValidationError):
            CursorParams(limit=201)


class TestCursorEncodeDecode:
    def test_encode_decode_roundtrip(self):
        dt = datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)
        id = uuid4()
        cursor = encode_cursor(dt, id)
        decoded_dt, decoded_id = decode_cursor(cursor)
        assert decoded_dt == dt
        assert decoded_id == id

    def test_naive_datetime_gets_utc(self):
        dt = datetime(2025, 6, 15, 10, 30, 0)
        id = uuid4()
        cursor = encode_cursor(dt, id)
        decoded_dt, decoded_id = decode_cursor(cursor)
        assert decoded_dt == dt.replace(tzinfo=UTC)
        assert decoded_id == id

    def test_different_uuids(self):
        dt = datetime.now(UTC)
        id1, id2 = uuid4(), uuid4()
        cursor1 = encode_cursor(dt, id1)
        cursor2 = encode_cursor(dt, id2)
        _, decoded_id1 = decode_cursor(cursor1)
        _, decoded_id2 = decode_cursor(cursor2)
        assert decoded_id1 == id1
        assert decoded_id2 == id2

    def test_decode_invalid_not_base64(self):
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor("!!!not-base64!!!")

    def test_decode_invalid_not_json(self):
        encoded = base64.urlsafe_b64encode(b"not json").decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor(encoded)

    def test_decode_invalid_missing_fields(self):
        payload = base64.urlsafe_b64encode(json.dumps({"foo": "bar"}).encode()).decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor(payload)

    def test_decode_invalid_uuid(self):
        payload = base64.urlsafe_b64encode(
            json.dumps({"created_at": "2025-06-15T10:30:00+00:00", "id": "not-a-uuid"}).encode()
        ).decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor(payload)

    def test_encode_output_format(self):
        dt = datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)
        id = uuid4()
        cursor = encode_cursor(dt, id)
        decoded_bytes = base64.urlsafe_b64decode(cursor.encode())
        payload = json.loads(decoded_bytes)
        assert payload["created_at"] == "2025-06-15T10:30:00+00:00"
        assert payload["id"] == str(id)
