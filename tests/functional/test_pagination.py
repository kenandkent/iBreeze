"""Pagination tests — cursor-based pagination helpers.

Covers design spec sections:
- G.17 Pagination (cursor-based, encode/decode)
"""
import uuid
from datetime import datetime, timezone

import pytest


class TestCursorPagination:
    """Cursor-based pagination encode/decode."""

    def test_cursor_pagination_basic(self):
        from ibreeze_backend.api.pagination import encode_cursor, decode_cursor

        now = datetime.now(timezone.utc)
        uid = uuid.uuid4()

        cursor = encode_cursor(now, uid)
        assert isinstance(cursor, str)
        assert len(cursor) > 0

        decoded_dt, decoded_id = decode_cursor(cursor)
        assert decoded_id == uid
        assert decoded_dt.tzinfo is not None

    def test_cursor_pagination_empty(self):
        from ibreeze_backend.api.pagination import CursorParams

        params = CursorParams()
        assert params.cursor is None
        assert params.limit == 50

    def test_cursor_pagination_has_more(self):
        from ibreeze_backend.api.pagination import encode_cursor, decode_cursor

        now = datetime.now(timezone.utc)
        uid = uuid.uuid4()

        cursor = encode_cursor(now, uid)
        dt, id_ = decode_cursor(cursor)
        assert id_ == uid
        assert dt.year == now.year

    def test_cursor_pagination_invalid_cursor(self):
        from ibreeze_backend.api.pagination import decode_cursor

        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor("not-a-valid-cursor!!!")

    def test_cursor_pagination_roundtrip(self):
        from ibreeze_backend.api.pagination import encode_cursor, decode_cursor

        dt = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        uid = uuid.uuid4()

        cursor = encode_cursor(dt, uid)
        decoded_dt, decoded_id = decode_cursor(cursor)
        assert decoded_id == uid
        assert decoded_dt.replace(microsecond=0) == dt.replace(microsecond=0)
