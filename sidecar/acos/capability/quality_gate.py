"""能力发版质量门禁。

五类检查（对照设计方案 §17 / 实施计划 P3-T5）：
  1. Manifest/Schema 校验（字段完整性）
  2. 依赖 Resolve（引用的 PromptAsset/Skill 版本必须存在且已发布）
  3. checksum / 依赖锁校验（Skill/PromptAsset 重算自身 checksum；
     Capability 调用 build_snapshot 重算完整依赖树与锁文件 checksum）
  4. Golden Case（预留接口，首版为空集合，始终通过）
  5. Prompt Injection / Secret Leakage 启发式静态检测

注意：第 5 类是启发式检测，不是完备防护，仅用于拦截明显模式。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import aiosqlite

from acos.capability.models import compute_checksum
from acos.capability.snapshot import CapabilitySnapshot


@dataclass
class QualityGateResult:
    passed: bool
    failed_checks: list[str] = field(default_factory=list)


class QualityGate:
    """执行质量门禁检查。"""

    _INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
        re.compile(r"system\s*:\s*", re.IGNORECASE),
        re.compile(r"<\|system\|>", re.IGNORECASE),
        re.compile(r"\[INST\]", re.IGNORECASE),
        re.compile(r"<<SYS>>", re.IGNORECASE),
    ]

    _SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{20,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9]{16,}"),
        re.compile(r"password\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    ]

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def run_quality_gate(
        self,
        entity_type: str,
        entity_id: str,
        version: int,
    ) -> QualityGateResult:
        failed_checks: list[str] = []

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            if not await self._check_manifest(db, entity_type, entity_id, version):
                failed_checks.append("manifest_validation")

            if not await self._check_dependencies(db, entity_type, entity_id, version):
                failed_checks.append("dependency_resolve")

            if not await self._check_checksum(db, entity_type, entity_id, version):
                failed_checks.append("checksum_validation")

            if not await self._check_golden_cases(db, entity_type, entity_id, version):
                failed_checks.append("golden_case")

            if not await self._check_prompt_injection(db, entity_type, entity_id, version):
                failed_checks.append("prompt_injection")

        return QualityGateResult(
            passed=len(failed_checks) == 0,
            failed_checks=failed_checks,
        )

    async def _load_version(
        self,
        db: aiosqlite.Connection,
        entity_type: str,
        entity_id: str,
        version: int,
    ) -> aiosqlite.Row | None:
        table = f"{entity_type}_versions"
        cursor = await db.execute(
            f"SELECT * FROM {table} WHERE {entity_type}_id = ? AND version = ?",
            (entity_id, version),
        )
        return await cursor.fetchone()

    async def _check_manifest(
        self,
        db: aiosqlite.Connection,
        entity_type: str,
        entity_id: str,
        version: int,
    ) -> bool:
        row = await self._load_version(db, entity_type, entity_id, version)
        if row is None:
            return False
        if not row["name"]:
            return False
        if entity_type == "skill":
            if not row["prompt_asset_id"]:
                return False
            if not row["checksum"]:
                return False
        elif entity_type == "prompt_asset":
            if not row["segments"]:
                return False
        elif entity_type == "capability":
            cursor = await db.execute(
                """SELECT COUNT(*) AS n FROM skill_bindings
                   WHERE capability_id = ? AND capability_version = ?""",
                (entity_id, version),
            )
            cnt = await cursor.fetchone()
            if cnt is None or cnt["n"] == 0:
                return False
        else:
            return False
        return True

    async def _check_dependencies(
        self,
        db: aiosqlite.Connection,
        entity_type: str,
        entity_id: str,
        version: int,
    ) -> bool:
        row = await self._load_version(db, entity_type, entity_id, version)
        if row is None:
            return False

        if entity_type == "skill":
            cursor = await db.execute(
                """SELECT status FROM prompt_asset_versions
                   WHERE prompt_asset_id = ? AND version = ?""",
                (row["prompt_asset_id"], row["prompt_asset_version"]),
            )
            dep = await cursor.fetchone()
            if dep is None or dep["status"] != "published":
                return False

        elif entity_type == "capability":
            bindings = json.loads(row["skill_bindings"])
            for binding in bindings:
                cursor = await db.execute(
                    """SELECT status FROM skill_versions
                       WHERE skill_id = ? AND version = ?""",
                    (binding["skill_id"], binding["skill_version"]),
                )
                dep = await cursor.fetchone()
                if dep is None or dep["status"] != "published":
                    return False

        return True

    async def _check_checksum(
        self,
        db: aiosqlite.Connection,
        entity_type: str,
        entity_id: str,
        version: int,
    ) -> bool:
        row = await self._load_version(db, entity_type, entity_id, version)
        if row is None:
            return False

        if entity_type == "prompt_asset":
            stored = row["checksum"]
            computed = compute_checksum({
                "name": row["name"],
                "segments": json.loads(row["segments"]),
                "variables": json.loads(row["variables"]),
                "context_slots": json.loads(row["context_slots"]),
            })
            return stored == computed

        if entity_type == "skill":
            stored = row["checksum"]
            computed = compute_checksum({
                "name": row["name"],
                "prompt_asset_id": row["prompt_asset_id"],
                "prompt_asset_version": row["prompt_asset_version"],
                "tool_bindings": json.loads(row["tool_bindings"]),
                "knowledge_refs": json.loads(row["knowledge_refs"]),
                "input_schema": json.loads(row["input_schema"]),
                "output_schema": json.loads(row["output_schema"]),
            })
            return stored == computed

        if entity_type == "capability":
            try:
                snapshot = CapabilitySnapshot()
                await snapshot.build_snapshot(db, entity_id, version)
            except ValueError:
                return False
            return True

        return False

    async def _check_golden_cases(
        self,
        db: aiosqlite.Connection,
        entity_type: str,
        entity_id: str,
        version: int,
    ) -> bool:
        return True

    async def _check_prompt_injection(
        self,
        db: aiosqlite.Connection,
        entity_type: str,
        entity_id: str,
        version: int,
    ) -> bool:
        if entity_type in ("skill", "capability"):
            cursor = await db.execute(
                """SELECT prompt_asset_id, prompt_asset_version
                   FROM skill_versions WHERE skill_id = ? AND version = ?""",
                (entity_id, version),
            )
            skill_row = await cursor.fetchone()
            if skill_row is None:
                return True
            cursor = await db.execute(
                """SELECT segments FROM prompt_asset_versions
                   WHERE prompt_asset_id = ? AND version = ?""",
                (skill_row["prompt_asset_id"], skill_row["prompt_asset_version"]),
            )
            asset_row = await cursor.fetchone()
            if asset_row is None:
                return True
            text = asset_row["segments"]
        elif entity_type == "prompt_asset":
            row = await self._load_version(db, entity_type, entity_id, version)
            if row is None:
                return True
            text = row["segments"]
        else:
            return True

        try:
            data = json.loads(text)
            flat = " ".join(str(v) for v in data.values() if isinstance(v, str))
        except (ValueError, TypeError):
            flat = str(text)

        for pattern in self._INJECTION_PATTERNS + self._SECRET_PATTERNS:
            if pattern.search(flat):
                return False
        return True
