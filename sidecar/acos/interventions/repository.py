"""HumanIntervention 仓库。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.interventions.models import HumanIntervention

# target_ref 格式白名单（设计 §5.7）
_VALID_TARGET_REF_RE = re.compile(
    r"^(company_dissolution|employee_drain|backend_recovery|approval|manual_task|dead_letter):[\w-]+$"
)


def _row_to_intervention(row: aiosqlite.Row) -> HumanIntervention:
    return HumanIntervention(
        intervention_id=row["intervention_id"],
        company_id=row["company_id"],
        task_id=row["task_id"],
        node_id=row["node_id"],
        run_id=row["run_id"],
        subtype=row["subtype"],
        target_ref=row["target_ref"],
        status=row["status"],
        allowed_actions=json.loads(row["allowed_actions"]),
        resolution_ref=row["resolution_ref"],
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
        trace_id=row["trace_id"],
        version=row["version"],
    )


class InterventionRepository:
    """HumanIntervention 仓库。"""

    async def create_or_get_open(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        subtype: str,
        target_ref: str,
        allowed_actions: list[str],
        trace_id: str,
        task_id: str | None = None,
        node_id: str | None = None,
        run_id: str | None = None,
    ) -> HumanIntervention:
        """创建或获取 open 的干预项（幂等）。

        target_ref 格式必须为 subtype:id，如 company_dissolution:abc123。
        """
        if not _VALID_TARGET_REF_RE.match(target_ref):
            raise ValueError(
                f"target_ref 格式无效: {target_ref!r}，"
                "必须为 subtype:id 格式，如 company_dissolution:<id>"
            )
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM human_interventions
               WHERE company_id = ? AND subtype = ? AND target_ref = ? AND status = 'open'
               LIMIT 1""",
            (company_id, subtype, target_ref),
        )
        row = await cursor.fetchone()
        if row is not None:
            return _row_to_intervention(row)

        intervention = HumanIntervention(
            company_id=company_id,
            task_id=task_id,
            node_id=node_id,
            run_id=run_id,
            subtype=subtype,
            target_ref=target_ref,
            status="open",
            allowed_actions=allowed_actions,
            trace_id=trace_id,
        )
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            """INSERT INTO human_interventions
               (intervention_id, company_id, task_id, node_id, run_id,
                subtype, target_ref, status, allowed_actions,
                resolution_ref, resolved_at, resolved_by,
                trace_id, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, NULL, NULL, NULL, ?, 1, ?, ?)""",
            (
                intervention.intervention_id,
                intervention.company_id,
                intervention.task_id,
                intervention.node_id,
                intervention.run_id,
                intervention.subtype,
                intervention.target_ref,
                json.dumps(intervention.allowed_actions),
                intervention.trace_id,
                now,
                now,
            ),
        )
        await conn.commit()
        return intervention

    async def get(
        self, conn: aiosqlite.Connection, intervention_id: str, company_id: str
    ) -> HumanIntervention | None:
        """获取干预项。"""
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM human_interventions WHERE intervention_id = ? AND company_id = ?",
            (intervention_id, company_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_intervention(row)

    async def list_open(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        subtype: str | None = None,
    ) -> list[HumanIntervention]:
        """列出 open 的干预项。"""
        conn.row_factory = aiosqlite.Row
        if subtype is not None:
            cursor = await conn.execute(
                """SELECT * FROM human_interventions
                   WHERE company_id = ? AND status = 'open' AND subtype = ?
                   ORDER BY created_at""",
                (company_id, subtype),
            )
        else:
            cursor = await conn.execute(
                """SELECT * FROM human_interventions
                   WHERE company_id = ? AND status = 'open'
                   ORDER BY created_at""",
                (company_id,),
            )
        rows = await cursor.fetchall()
        return [_row_to_intervention(r) for r in rows]

    async def resolve_cas(
        self,
        conn: aiosqlite.Connection,
        intervention_id: str,
        company_id: str,
        expected_version: int,
        resolution_ref: str,
        resolved_by: str,
    ) -> bool:
        """CAS 解决干预项。成功返回 True，版本冲突返回 False。"""
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            """UPDATE human_interventions
               SET status = 'resolved',
                   resolution_ref = ?,
                   resolved_by = ?,
                   resolved_at = ?,
                   version = version + 1,
                   updated_at = ?
               WHERE intervention_id = ?
                 AND company_id = ?
                 AND version = ?
                 AND status = 'open'""",
            (resolution_ref, resolved_by, now, now, intervention_id, company_id, expected_version),
        )
        await conn.commit()
        return cursor.rowcount == 1
