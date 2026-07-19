"""统一错误码体系测试。"""

from __future__ import annotations

import os

import pytest

from acos.rpc.errors import (
    ALL_ERROR_CODES,
    AcosError,
    BACKEND_UNAVAILABLE,
    ORG_VALIDATION,
    SYS_INTERNAL,
    create_error,
)
from acos.rpc.server import RPCServer


# ── helpers ──────────────────────────────────────────────────────────────


@pytest.fixture
def socket_path() -> str:
    path = f"/tmp/acos_err_test_{os.getpid()}_{id(object())}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


async def _send_and_recv(
    socket_path: str,
    method: str,
    params: dict,
    req_id: str = "test-1",
) -> dict:
    import asyncio
    import json

    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        request = {
            "type": "request",
            "id": req_id,
            "method": method,
            "params": params,
        }
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()

        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        return json.loads(line.decode())
    finally:
        writer.close()
        await writer.wait_closed()


# ── unit tests ───────────────────────────────────────────────────────────


def test_acos_error_to_dict() -> None:
    err = AcosError(
        code="ORG-VALIDATION",
        message="必填字段缺失",
        cause="name 为空",
        suggestion="补充 name 字段",
        trace_id="t-001",
    )
    d = err.to_dict()
    assert d["code"] == "ORG-VALIDATION"
    assert d["message"] == "必填字段缺失"
    assert d["cause"] == "name 为空"
    assert d["suggestion"] == "补充 name 字段"
    assert d["trace_id"] == "t-001"


def test_create_error_uses_template_defaults() -> None:
    err = create_error(ORG_VALIDATION, "", trace_id="t-002")
    assert err.code == ORG_VALIDATION
    assert err.message == "组织数据校验失败"
    assert err.suggestion == "检查必填字段"
    assert err.trace_id == "t-002"


def test_create_error_override_template() -> None:
    err = create_error(BACKEND_UNAVAILABLE, "自定义消息", cause="DNS 解析失败")
    assert err.message == "自定义消息"
    assert err.cause == "DNS 解析失败"


def test_error_codes_are_unique() -> None:
    codes = list(ALL_ERROR_CODES.keys())
    assert len(codes) == len(set(codes))


def test_error_code_prefixes() -> None:
    expected_prefixes = {
        "ORG": [
            "ORG-VALIDATION", "ORG-NOT-FOUND", "ORG-STATE-INVALID",
            "ORG-PERM-DENIED", "ORG-DEPT-CYCLE", "ORG-COMPANY-DISSOLVED",
        ],
        "CAP": [
            "CAP-VALIDATION", "CAP-VERSION-IMMUTABLE",
            "CAP-SNAPSHOT-CHECKSUM-MISMATCH", "CAP-QUALITY-GATE-FAILED",
        ],
        "ASSET": [
            "ASSET-CROSS-COMPANY-REF-DENIED", "TEMPLATE-CROSS-COMPANY-DENIED",
        ],
        "WF": ["WF-BUDGET-EXCEEDED", "WF-FIX-MAX-ROUNDS"],
        "RT": [
            "RT-SESSION-BUSY", "RT-SESSION-STALE",
            "RT-SESSION-READONLY", "RT-RESUME-FAILED",
        ],
        "PROV": ["PROV-UNAVAILABLE", "PROV-AUTH-INVALID", "PROV-BUDGET-FROZEN"],
        "BACKEND": [
            "BACKEND-UNAVAILABLE", "BACKEND-CAPACITY-FULL", "BACKEND-DRAINING",
            "BACKEND-PATH-DENIED", "BACKEND-RECOVERY-UNSAFE", "BACKEND-QUEUE-TIMEOUT",
        ],
        "KG": [
            "KG-EXTRACT-FAILED", "KG-EMBED-VERSION-MISMATCH",
            "KG-CLOUD-CONSENT-REQUIRED",
        ],
        "GOV": [
            "GOV-APPROVAL-REJECTED", "GOV-BUDGET-CURRENCY-INVALID",
            "GOV-BUDGET-LIMIT-INVALID", "GOV-BUDGET-POLICY-INVALID",
        ],
        "SYS": [
            "SYS-INTERNAL", "SYS-OPTIMISTIC-LOCK-CONFLICT", "SYS-IDEMPOTENCY-CONFLICT",
            "SYS-MIGRATION-FAILED", "SYS-BACKUP-IN-PROGRESS", "SYS-BACKUP-QUIESCE-TIMEOUT",
            "SYS-BACKUP-INCOMPATIBLE", "SYS-BACKUP-INCONSISTENT", "SYS-BACKUP-NOT-FOUND",
            "SYS-UPDATE-FAILED", "SYS-UPDATE-SIGNATURE-INVALID", "SYS-BOOTSTRAP-ROOT-INVALID",
        ],
    }
    for prefix, codes in expected_prefixes.items():
        for code in codes:
            assert code in ALL_ERROR_CODES, f"{code} not found in ALL_ERROR_CODES"
            if prefix == "ASSET":
                assert code.startswith("ASSET") or code.startswith("TEMPLATE")
            else:
                assert code.startswith(prefix)


def test_backend_error_not_misclassified() -> None:
    """BACKEND-* 错误码不应被归入其他前缀。"""
    backend_codes = [k for k in ALL_ERROR_CODES if k.startswith("BACKEND")]
    assert len(backend_codes) == 14
    for code in backend_codes:
        assert code not in ALL_ERROR_CODES or ALL_ERROR_CODES[code]["code"] == code


# ── integration: RPC dispatch ────────────────────────────────────────────


async def test_rpc_method_raises_acos_error(socket_path: str) -> None:
    server = RPCServer(socket_path=socket_path)

    async def _fail_handler(_params: dict) -> dict:
        raise create_error(ORG_VALIDATION, "必填字段缺失", cause="name 为空")

    server.register_method("test.fail", _fail_handler)
    await server.start()
    try:
        resp = await _send_and_recv(socket_path, "test.fail", {}, "r1")
        assert resp["id"] == "r1"
        assert resp["result"] is None
        err = resp["error"]
        assert isinstance(err, dict)
        assert err["code"] == "ORG-VALIDATION"
        assert err["message"] == "必填字段缺失"
        assert err["cause"] == "name 为空"
        assert "suggestion" in err
        assert "trace_id" in err
    finally:
        await server.stop()


async def test_unexpected_exception_becomes_sys_internal(socket_path: str) -> None:
    server = RPCServer(socket_path=socket_path)

    async def _boom_handler(_params: dict) -> dict:
        raise RuntimeError("something unexpected")

    server.register_method("test.boom", _boom_handler)
    await server.start()
    try:
        resp = await _send_and_recv(socket_path, "test.boom", {}, "r2")
        assert resp["id"] == "r2"
        assert resp["result"] is None
        err = resp["error"]
        assert isinstance(err, dict)
        assert err["code"] == SYS_INTERNAL
        assert err["message"] == "系统内部错误"
        assert "RuntimeError" not in str(err)
    finally:
        await server.stop()
