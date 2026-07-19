"""Transcript 与上下文摘要（Phase 7-T1）。

- transcript.jsonl 固定行 schema + canonical checksum + Provider 格式归一化。
- context-summary.md 按 20 条/8000 token 任一先到生成，NFC/LF 规范，不调模型。

所有规范化与 hash 均确定性，可单测。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable

# transcript 行固定 schema 版本
TRANSCRIPT_SCHEMA_VERSION: str = "acos:transcript:v1"
CONVERSATION_EVENT_SCHEMA_VERSION: str = "acos:conversation-event:v1"

# 摘要生成参数
SUMMARY_MAX_EVENTS: int = 20
SUMMARY_MAX_TOKENS: int = 8000
TOKEN_EST_WORDS_PER_TOKEN: float = 0.75  # 粗略：1 token ≈ 0.75 词

# 三个策略域前缀（严格照抄设计方案 §11.4）
WORKSPACE_POLICY_DOMAIN: str = "acos:workspace-policy:v1\n"
SECURITY_POLICY_DOMAIN: str = "acos:security-policy:v1\n"
EFFECTIVE_GRANTS_DOMAIN: str = "acos:effective-grants:v1\n"

_EMPTY_GRANTS_DIGEST_INPUT: str = EFFECTIVE_GRANTS_DOMAIN + "[]"


def canonical_json(obj: Any) -> str:
    """RFC 8785 风格规范化 JSON：对象键递归排序，数组保序，无尾部空白。"""
    return json.dumps(_sort_keys(obj), ensure_ascii=False, separators=(",", ":"))


def _sort_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sort_keys(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_sort_keys(v) for v in obj]
    return obj


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_workspace_policy_hash(workspace_policy: dict) -> str:
    """域前缀 + RFC8785 canonical JSON 后 SHA-256。"""
    return _sha256(WORKSPACE_POLICY_DOMAIN + canonical_json(workspace_policy or {}))


def compute_security_policy_hash(security_policy: dict) -> str:
    return _sha256(SECURITY_POLICY_DOMAIN + canonical_json(security_policy or {}))


def compute_effective_grants_hash(grants: Iterable[dict]) -> str:
    """按 grant_id + expires_at 排序；空集合固定为 SHA256(domain + '[]')。"""
    items = list(grants or [])
    if not items:
        return _sha256(_EMPTY_GRANTS_DIGEST_INPUT)
    normalized = []
    for g in items:
        normalized.append({
            "grant_id": g.get("grant_id", ""),
            "target_type": g.get("target_type", ""),
            "target_id": g.get("target_id", ""),
            "permission": g.get("permission", ""),
            "expires_at": g.get("expires_at", ""),
        })
    normalized.sort(key=lambda x: (x["grant_id"], x["expires_at"]))
    return _sha256(EFFECTIVE_GRANTS_DOMAIN + canonical_json(normalized))


def compute_security_context_key(
    company_id: str,
    department_id: str,
    task_id: str | None,
    capability_snapshot_checksum: str,
    provider_id: str,
    model_id: str,
    workspace_policy_hash: str,
    security_policy_hash: str,
    effective_grants_hash: str,
) -> str:
    """九维安全上下文 key：九个维度按固定顺序 canonical 后 SHA-256。

    任一维度变化都产生不同 key → 新上下文线程。
    """
    dims = [
        ("company_id", company_id or ""),
        ("department_id", department_id or ""),
        ("task_id", task_id or ""),
        ("capability_snapshot_checksum", capability_snapshot_checksum or ""),
        ("provider_id", provider_id or ""),
        ("model_id", model_id or ""),
        ("workspace_policy_hash", workspace_policy_hash or ""),
        ("security_policy_hash", security_policy_hash or ""),
        ("effective_grants_hash", effective_grants_hash or ""),
    ]
    payload = canonical_json({k: v for k, v in dims})
    return _sha256("acos:security-context:v1\n" + payload)


def estimate_tokens(text: str) -> int:
    """粗略 token 估计（确定性，仅用于预算裁剪，不调模型）。"""
    words = re.findall(r"\S+", text or "")
    return max(1, int(len(words) / TOKEN_EST_WORDS_PER_TOKEN))


def normalize_provider_event(event: dict) -> dict:
    """Provider 格式归一化：把 Provider 原生事件映射为统一 transcript 行。

    统一字段：event_type / role / content / tool_name / tool_request_hash /
    artifact_ref / token_estimate。
    """
    etype = event.get("event_type") or event.get("type") or "message"
    content = event.get("content") or event.get("text") or ""
    role = event.get("role") or ""
    tool_name = event.get("tool_name") or event.get("tool") or None
    tool_request_hash = event.get("tool_request_hash")
    artifact_ref = event.get("artifact_ref")
    if tool_request_hash is None and tool_name is not None:
        tool_request_hash = _sha256(canonical_json(event.get("tool_input", {})))
    return {
        "event_type": etype,
        "role": role,
        "content": content,
        "tool_name": tool_name,
        "tool_request_hash": tool_request_hash,
        "artifact_ref": artifact_ref,
        "token_estimate": estimate_tokens(content),
    }


def build_transcript_line(
    sequence: int,
    event_type: str,
    role: str,
    content: str,
    *,
    tool_name: str | None = None,
    tool_request_hash: str | None = None,
    artifact_ref: str | None = None,
    token_estimate: int = 0,
    provider_native_event_id: str | None = None,
) -> dict:
    """构造一条固定 schema 的 transcript 行（尚未写盘）。"""
    line = {
        "schema_version": TRANSCRIPT_SCHEMA_VERSION,
        "sequence": sequence,
        "event_type": event_type,
        "role": role,
        "content": content,
        "tool_name": tool_name,
        "tool_request_hash": tool_request_hash,
        "artifact_ref": artifact_ref,
        "token_estimate": token_estimate,
        "provider_native_event_id": provider_native_event_id,
    }
    line["canonical_checksum"] = _sha256(canonical_json(line))
    return line


def transcript_line_checksum(line: dict) -> str:
    """对一行（去除 checksum 字段后）重算 canonical checksum，供 fail-closed 校验。"""
    base = {k: v for k, v in line.items() if k != "canonical_checksum"}
    return _sha256(canonical_json(base))


def build_context_summary(lines: list[dict]) -> str:
    """生成 context-summary.md 内容。

    按 20 条/8000 token 任一先到截断；固定 front matter、NFC/LF/空白规范。
    不调用模型。
    """
    selected: list[dict] = []
    total_tokens = 0
    for line in lines:
        t = int(line.get("token_estimate", 0))
        if len(selected) >= SUMMARY_MAX_EVENTS:
            break
        if total_tokens + t > SUMMARY_MAX_TOKENS and selected:
            break
        selected.append(line)
        total_tokens += t

    blocks: list[str] = []
    blocks.append("---")
    blocks.append("schema_version: acos:context-summary:v1")
    blocks.append(f"event_count: {len(selected)}")
    blocks.append(f"token_estimate: {total_tokens}")
    blocks.append("---")
    blocks.append("")
    blocks.append("# 会话上下文摘要")
    blocks.append("")
    for line in selected:
        role = line.get("role") or line.get("event_type") or "system"
        content = _normalize_text(line.get("content", ""))
        if line.get("event_type") == "tool_use" or line.get("tool_name"):
            blocks.append(f"- **tool:{line.get('tool_name')}** ({role})")
            if content:
                blocks.append(f"  - {content}")
        else:
            blocks.append(f"- **{role}**: {content}")
    return "\n".join(blocks) + "\n"


def _normalize_text(text: str) -> str:
    """NFC 归一 + LF 换行 + 压缩多余空白。"""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()
