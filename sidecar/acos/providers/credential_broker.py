"""Credential Broker 骨架（设计方案 §11.2 / §12.3）。

原则：
- 凭据不落明文到 Sidecar 持久层：明文只在进程内 secret 后端（v1 可测桩）短暂持有。
- 按 (company_id, provider_id, credential_slot) 隔离；同 Provider 多公司互不覆盖。
- API Provider 经 Broker 取 token；CLI Provider 用官方登录态，不走此通道。
- 取值只在调用栈内持有，用完丢弃引用；不写入变量之外的存储，不进子进程环境。

v1 用进程内 SecretBackend 抽象（KeyringSecretBackend / InMemorySecretBackend），
真实可测，不要求真实第三方登录。生产由 Rust Keychain 后端替换。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import aiosqlite

from acos.rpc.errors import AcosError

# 本地新增错误码（不改 errors.py）
CRED_NOT_FOUND = "CRED-NOT-FOUND"
CRED_VALIDATION = "CRED-VALIDATION"
CRED_SCOPE_DENIED = "CRED-SCOPE-DENIED"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(company_id: str, provider_id: str, credential_slot: str) -> str:
    return f"{company_id}\x1f{provider_id}\x1f{credential_slot}"


class SecretBackend(ABC):
    """明文密钥后端抽象。明文只在此后端持有，不写入 Sidecar DB。"""

    @abstractmethod
    def store(self, company_id: str, provider_id: str, credential_slot: str, secret: str) -> None: ...

    @abstractmethod
    def load(self, company_id: str, provider_id: str, credential_slot: str) -> str | None: ...

    @abstractmethod
    def delete(self, company_id: str, provider_id: str, credential_slot: str) -> None: ...


class InMemorySecretBackend(SecretBackend):
    """进程内内存后端（测试/开发用）。凭据只在内存，进程退出即失效。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def store(self, company_id: str, provider_id: str, credential_slot: str, secret: str) -> None:
        self._store[_key(company_id, provider_id, credential_slot)] = secret

    def load(self, company_id: str, provider_id: str, credential_slot: str) -> str | None:
        return self._store.get(_key(company_id, provider_id, credential_slot))

    def delete(self, company_id: str, provider_id: str, credential_slot: str) -> None:
        self._store.pop(_key(company_id, provider_id, credential_slot), None)


class KeyringSecretBackend(SecretBackend):
    """基于 OS keyring 的后端（若 keyring 可用）。生产由 Rust Keychain 代理替换。"""

    _SERVICE = "ibreeze-credential-broker"

    def __init__(self) -> None:
        try:
            import keyring  # type: ignore
            self._keyring = keyring
        except ImportError as exc:  # pragma: no cover - 环境无 keyring 时
            raise AcosError(
                CRED_VALIDATION,
                "keyring 后端不可用",
                cause=str(exc),
                suggestion="安装 keyring 或使用 InMemorySecretBackend",
            )

    def store(self, company_id: str, provider_id: str, credential_slot: str, secret: str) -> None:
        self._keyring.set_password(self._SERVICE, _key(company_id, provider_id, credential_slot), secret)

    def load(self, company_id: str, provider_id: str, credential_slot: str) -> str | None:
        return self._keyring.get_password(self._SERVICE, _key(company_id, provider_id, credential_slot))

    def delete(self, company_id: str, provider_id: str, credential_slot: str) -> None:
        try:
            self._keyring.delete_password(self._SERVICE, _key(company_id, provider_id, credential_slot))
        except Exception:  # pragma: no cover - 不存在时忽略
            pass


class CredentialBroker:
    """Credential Broker：管理凭据引用元数据 + 通过 SecretBackend 存取明文。"""

    def __init__(self, db_path: str, backend: SecretBackend | None = None) -> None:
        self._db_path = db_path
        self._backend = backend or InMemorySecretBackend()

    async def set_credential(
        self,
        company_id: str,
        provider_id: str,
        credential_slot: str,
        secret: str,
    ) -> dict:
        """写入/更新凭据。明文入 SecretBackend，DB 只记录引用元数据。"""
        if not company_id or not provider_id or not credential_slot:
            raise AcosError(CRED_VALIDATION, "凭据键不完整")
        if not isinstance(secret, str) or not secret:
            raise AcosError(CRED_VALIDATION, "凭据明文不能为空")

        self._backend.store(company_id, provider_id, credential_slot, secret)

        conn = await aiosqlite.connect(self._db_path)
        try:
            now = _now_utc()
            await conn.execute(
                """INSERT INTO provider_credential_refs
                   (company_id, provider_id, credential_slot, backend, created_at, updated_at, revoked_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(company_id, provider_id, credential_slot) DO UPDATE SET
                       updated_at = excluded.updated_at,
                       revoked_at = NULL""",
                (company_id, provider_id, credential_slot,
                 type(self._backend).__name__, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"ok": True}

    async def get_credential(
        self,
        company_id: str,
        provider_id: str,
        credential_slot: str,
    ) -> str:
        """Broker 取值通道：返回明文。调用方只在本次请求栈内持有。

        跨公司/未知/已吊销 fail-closed。
        """
        if not company_id or not provider_id or not credential_slot:
            raise AcosError(CRED_VALIDATION, "凭据键不完整")

        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                """SELECT * FROM provider_credential_refs
                   WHERE company_id = ? AND provider_id = ? AND credential_slot = ?""",
                (company_id, provider_id, credential_slot),
            )
            row = await cur.fetchone()
        finally:
            await conn.close()

        if row is None or row["revoked_at"] is not None:
            raise AcosError(
                CRED_NOT_FOUND,
                "凭据不存在或已吊销",
                cause=f"{company_id}/{provider_id}/{credential_slot}",
            )

        secret = self._backend.load(company_id, provider_id, credential_slot)
        if secret is None:
            raise AcosError(CRED_NOT_FOUND, "凭据后端无明文", cause="backend miss")
        return secret

    async def revoke_credential(
        self,
        company_id: str,
        provider_id: str,
        credential_slot: str,
    ) -> dict:
        """吊销凭据：从 SecretBackend 删除明文并标记引用 revoked。"""
        if not company_id or not provider_id or not credential_slot:
            raise AcosError(CRED_VALIDATION, "凭据键不完整")

        conn = await aiosqlite.connect(self._db_path)
        try:
            cur = await conn.execute(
                """SELECT 1 FROM provider_credential_refs
                   WHERE company_id = ? AND provider_id = ? AND credential_slot = ?
                     AND revoked_at IS NULL""",
                (company_id, provider_id, credential_slot),
            )
            if await cur.fetchone() is None:
                raise AcosError(CRED_NOT_FOUND, "凭据不存在", cause=credential_slot)
            await conn.execute(
                """UPDATE provider_credential_refs SET revoked_at = ?, updated_at = ?
                   WHERE company_id = ? AND provider_id = ? AND credential_slot = ?""",
                (_now_utc(), _now_utc(), company_id, provider_id, credential_slot),
            )
            await conn.commit()
        finally:
            await conn.close()

        self._backend.delete(company_id, provider_id, credential_slot)
        return {"ok": True}
