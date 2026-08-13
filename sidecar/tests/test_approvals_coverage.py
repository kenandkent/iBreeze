"""Cover approvals/service branches the main suite does not reach.

Targets the field-validator raises (sha256/uuid/timestamp), the
external-write request guard errors and the unknown-decision resolution path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ibreeze.approvals import service

C1 = "00000000-0000-0000-0000-000000000001"
C2 = "00000000-0000-0000-0000-000000000002"
HASH = "a" * 64


class TestValidateSha256:
    def test_raises_when_required_and_missing(self) -> None:
        with pytest.raises(ValueError, match="EXPECTED_OLD_SHA256_INVALID"):
            service._validate_sha256(None, required=True, field="expected_old_sha256")

    def test_raises_on_malformed_value(self) -> None:
        with pytest.raises(ValueError, match="SOURCE_SHA256_INVALID"):
            service._validate_sha256("not-a-hash", required=True, field="source_sha256")


class TestValidateUuid:
    def test_raises_on_invalid_uuid(self) -> None:
        with pytest.raises(ValueError, match="RUN_ID_INVALID"):
            service._validate_uuid("not-a-uuid", "run_id")


class TestValidateTimestamp:
    def test_raises_on_unparseable_timestamp(self) -> None:
        with pytest.raises(ValueError, match="PRIOR_STARTED_AT_INVALID"):
            service._validate_timestamp("not-a-date", "prior_started_at")

    def test_raises_on_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="PRIOR_STARTED_AT_INVALID"):
            service._validate_timestamp("2026-01-01T00:00:00", "prior_started_at")


class TestRequestExternalWriteApproval:
    async def test_raises_for_relative_target_path(self) -> None:
        with pytest.raises(ValueError, match="TARGET_PATH_INVALID"):
            await service.request_external_write_approval(
                AsyncMock(),
                C1,
                run_id=C2,
                workspace_grant_id="g1",
                target_realpath="relative/path",
                operation="create_file",
                expected_old_sha256=None,
                source_sha256=HASH,
            )

    async def test_raises_for_unknown_operation(self) -> None:
        with pytest.raises(ValueError, match="OPERATION_INVALID"):
            await service.request_external_write_approval(
                AsyncMock(),
                C1,
                run_id=C2,
                workspace_grant_id="g1",
                target_realpath="/tmp/x",
                operation="chmod",
                expected_old_sha256=None,
                source_sha256=HASH,
            )

    async def test_raises_when_source_sha256_provided_for_delete(self) -> None:
        with pytest.raises(ValueError, match="SOURCE_SHA256_INVALID"):
            await service.request_external_write_approval(
                AsyncMock(),
                C1,
                run_id=C2,
                workspace_grant_id="g1",
                target_realpath="/tmp/x",
                operation="delete_file",
                expected_old_sha256=HASH,
                source_sha256=HASH,
            )


class TestResolveApproval:
    async def test_raises_for_unknown_decision(self) -> None:
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"id": "a1", "status": "pending"})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=cursor)
        with pytest.raises(ValueError, match="VALIDATION_FAILED"):
            await service.resolve_approval(db, C1, approval_id="a1", decision="maybe")
