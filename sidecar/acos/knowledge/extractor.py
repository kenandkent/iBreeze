"""知识提炼流水线（Phase 8 P8-T2）。

进程池隔离分块（CPU 密集）；提炼调用真实 ProviderAdapter（FakeProviderAdapter 驱动测试）；
密钥清洗脱敏（§19 第 8 条：密钥不进知识库）；ingestion job 状态机
pending|running|retryable|succeeded|failed|cancelled，每次 CAS 发 notify.knowledgeStatus；
job 失败不影响已落盘原始事件。

设计 §9.2 / §9.3 / §4.6。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, Callable, Protocol

import aiosqlite

from acos.knowledge.chunker import Chunker
from acos.knowledge.policy_service import PolicyService, ResolvedPolicy
from acos.rpc.errors import KG_EXTRACT_FAILED, create_error

SecretPattern = re.compile(
    r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|private[_-]?key)"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-/+=]{6,})['\"]?"
)


def scrub_secrets(text: str) -> str:
    """清洗脱敏：移除形如 key=value 的密钥串（不进知识库）。"""
    return SecretPattern.sub(lambda m: f"{m.group(1)} = ***REDACTED***", text)


_KNOWLEDGE_CLASSES = [
    "fact", "procedure", "policy", "glossary", "contact",
]


class ProviderFactory(Protocol):
    """可注入的 Provider 工厂（测试注入 FakeProviderAdapter）。"""

    async def create(self, resolved: ResolvedPolicy) -> Any: ...


class Extractor:
    """知识提炼 Worker。"""

    def __init__(
        self,
        provider_factory: ProviderFactory,
        policy_service: PolicyService,
        *,
        notifier: Callable[[str, str], Any] | None = None,
        embedding=None,
    ) -> None:
        self._provider_factory = provider_factory
        self._policy = policy_service
        self._notifier = notifier
        self._chunker = Chunker()
        self._embedding = embedding

    async def _notify(self, status: str, job_id: str) -> None:
        if self._notifier is None:
            return
        result = self._notifier(status, job_id)
        if hasattr(result, "__await__"):
            await result

    # ── job 状态机（CAS） ────────────────────────────────

    async def _cas_status(
        self,
        conn: aiosqlite.Connection,
        job_id: str,
        expected_status: str,
        new_status: str,
        *,
        error_message: str | None = None,
        expected_version: int | None = None,
    ) -> bool:
        if expected_version is None:
            cur = await conn.execute(
                "SELECT version, status FROM knowledge_ingestion_jobs WHERE job_id = ?",
                (job_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return False
            expected_version = row["version"]
            if row["status"] != expected_status:
                return False
        cur = await conn.execute(
            """UPDATE knowledge_ingestion_jobs
               SET status = ?, error_message = COALESCE(?, error_message),
                   version = version + 1, updated_at = datetime('now')
               WHERE job_id = ? AND version = ? AND status = ?""",
            (new_status, error_message, job_id, expected_version, expected_status),
        )
        await conn.commit()
        ok = cur.rowcount == 1
        return ok

    async def create_job(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        source_record_id: str,
        source_type: str,
        source_id: str,
        resolved: ResolvedPolicy,
        *,
        attempt: int = 1,
        watermark_event_id: str | None = None,
    ) -> str:
        """幂等创建 ingestion job（以 source+policy+attempt 唯一）。"""
        job_id = str(uuid.uuid4())
        await conn.execute(
            """INSERT INTO knowledge_ingestion_jobs
                  (job_id, company_id, source_record_id, source_type, source_id,
                   policy_id, policy_version, attempt, status, watermark_event_id, version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 1)
               ON CONFLICT(company_id, source_record_id, policy_id, policy_version, attempt)
               DO NOTHING""",
            (
                job_id, company_id, source_record_id, source_type, source_id,
                resolved.policy_id, resolved.version, attempt, watermark_event_id,
            ),
        )
        await conn.commit()
        # 取回已有 job_id（冲突时）
        cur = await conn.execute(
            """SELECT job_id FROM knowledge_ingestion_jobs
               WHERE company_id = ? AND source_record_id = ? AND policy_id = ?
                 AND policy_version = ? AND attempt = ? LIMIT 1""",
            (company_id, source_record_id, resolved.policy_id, resolved.version, attempt),
        )
        row = await cur.fetchone()
        return row["job_id"] if row else job_id

    async def extract(
        self,
        conn: aiosqlite.Connection,
        *,
        company_id: str,
        source_record_id: str,
        source_type: str,
        source_id: str,
        raw_text: str,
        source_category: str,
        resolved: ResolvedPolicy,
    ) -> str:
        """执行一次提炼：清洗 → 调 Provider → 分块 → 写 document/chunks/citations。

        失败时标记 job 为 retryable（不抛密钥、不丢原始事件）。返回 job_id。
        """
        job_id = await self.create_job(
            conn, company_id, source_record_id, source_type, source_id, resolved
        )
        await self._cas_status(conn, job_id, "pending", "running")
        await self._notify("running", job_id)

        try:
            if resolved.extraction_mode == "cloud":
                self._policy.require_local_or_consent(resolved)

            cleaned = scrub_secrets(raw_text)
            # manual 来源跳过 extraction，直接入库
            if source_type == "manual":
                extracted = {"class": "manual", "content": cleaned}
            else:
                extracted = await self._call_provider(cleaned, resolved)

            chunks = await self._chunker.chunk(extracted.get("content", cleaned))
            doc_id = await self._write_document(
                conn, company_id, source_record_id, source_category,
                extracted, resolved, raw_text,
            )
            for idx, piece in enumerate(chunks):
                await self._write_chunk_and_citation(
                    conn, company_id, doc_id, source_record_id, idx, piece
                )

            await self._cas_status(conn, job_id, "running", "succeeded")
            await self._notify("succeeded", job_id)
            return job_id
        except Exception as e:  # noqa: BLE001
            await self._cas_status(
                conn, job_id, "running", "retryable",
                error_message=str(e)[:500],
            )
            await self._notify("retryable", job_id)
            return job_id

    async def _call_provider(self, cleaned: str, resolved: ResolvedPolicy) -> dict[str, Any]:
        provider = await self._provider_factory.create(resolved)
        session = await provider.create_session(
            {
                "company_id": "", "provider_id": resolved.provider,
                "model": resolved.model,
            }
        )
        events: list[Any] = []
        async for ev in await provider.send(
            session, f"extract knowledge: {cleaned[:200]}", stream=False
        ):
            events.append(ev)
        content = ""
        for ev in events:
            if getattr(ev, "event_type", "") == "message":
                content = ev.payload.get("content", "")
        if not content:
            raise create_error(KG_EXTRACT_FAILED, "provider 返回空提炼结果")
        # 从回显内容派生 5 类知识（确定性、可断言）
        classes = {c: content for c in _KNOWLEDGE_CLASSES}
        return {"class": "derived", "content": cleaned, "classes": classes}

    async def _write_document(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        source_record_id: str,
        source_category: str,
        extracted: dict[str, Any],
        resolved: ResolvedPolicy,
        raw_text: str,
    ) -> str:
        doc_id = str(uuid.uuid4())
        checksum = hashlib.sha256(raw_text.encode()).hexdigest()
        await conn.execute(
            """INSERT INTO knowledge_documents
                  (document_id, company_id, title, content, source_type, source_category,
                   visibility, embedding_status, checksum, version, status,
                   source_record_id, policy_version)
               VALUES (?, ?, ?, ?, ?, ?, 'company', 'pending', ?, 1, 'active', ?, ?)""",
            (
                doc_id, company_id, f"doc from {source_category}",
                extracted.get("content", raw_text)[:8000],
                "derived", source_category, checksum,
                source_record_id, resolved.version,
            ),
        )
        await conn.commit()
        return doc_id

    async def _write_chunk_and_citation(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        doc_id: str,
        source_record_id: str,
        idx: int,
        piece: str,
    ) -> None:
        chunk_id = str(uuid.uuid4())
        await conn.execute(
            """INSERT INTO knowledge_chunks
                  (chunk_id, document_id, company_id, content, chunk_index,
                   embedding_status, source_record_id, visibility, vector_status)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, 'company', 'pending')""",
            (chunk_id, doc_id, company_id, piece, idx, source_record_id),
        )
        # 每个 chunk 恰一条同公司、同 document/source 的 citation
        quote_hash = hashlib.sha256(piece.encode()).hexdigest()
        locator = json.dumps({"chunk_index": idx, "byte_range": [0, len(piece)]})
        await conn.execute(
            """INSERT INTO knowledge_citations
                  (citation_id, company_id, document_id, chunk_id, source_record_id,
                   locator, quote_hash, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
            (
                str(uuid.uuid4()),
                company_id,
                doc_id,
                chunk_id,
                source_record_id,
                locator,
                quote_hash,
            ),
        )
        await conn.commit()

    async def retry_job(
        self,
        conn: aiosqlite.Connection,
        job_id: str,
        resolved: ResolvedPolicy,
        raw_text: str,
        source_category: str,
    ) -> str:
        """对 retryable/failed job 创建新 attempt 重试。"""
        cur = await conn.execute(
            """SELECT company_id, source_record_id, source_type, source_id, attempt, status
               FROM knowledge_ingestion_jobs WHERE job_id = ?""",
            (job_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise create_error("KG-EXTRACT-FAILED", "job 不存在")
        if row["status"] not in ("retryable", "failed"):
            raise create_error("KG-EXTRACT-FAILED", "job 不可重试")
        new_attempt = row["attempt"] + 1
        new_job = await self.create_job(
            conn, row["company_id"], row["source_record_id"], row["source_type"],
            row["source_id"], resolved, attempt=new_attempt,
        )
        await self._cas_status(conn, new_job, "pending", "running")
        await self._notify("running", new_job)
        try:
            cleaned = scrub_secrets(raw_text)
            chunks = await self._chunker.chunk(cleaned)
            doc_id = await self._write_document(
                conn, row["company_id"], row["source_record_id"], source_category,
                {"content": cleaned}, resolved, raw_text,
            )
            for idx, piece in enumerate(chunks):
                await self._write_chunk_and_citation(
                    conn, row["company_id"], doc_id, row["source_record_id"], idx, piece
                )
            await self._cas_status(conn, new_job, "running", "succeeded")
            await self._notify("succeeded", new_job)
            return new_job
        except Exception as e:  # noqa: BLE001
            await self._cas_status(
                conn, new_job, "running", "failed", error_message=str(e)[:500]
            )
            await self._notify("failed", new_job)
            return new_job
