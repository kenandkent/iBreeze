#!/usr/bin/env python3
"""Generate the deterministic, redacted 200-task routing acceptance set."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "routing"
MANIFEST = ROOT / "tests" / "fixtures" / "routing-golden-tasks.v1.json"
CATEGORIES = (
    ("code_implementation", "task_execution", ("workspace.read", "workspace.write"), "execution_report"),
    ("code_review", "review", ("workspace.read",), "review_report"),
    ("document_design", "company_plan", ("workspace.read",), "design_document"),
    ("structured_schema", "verification", ("workspace.read", "schema.validate"), "verification_report"),
    ("tool_failure_recovery", "repair", ("workspace.read", "workspace.write", "test.run"), "repair_report"),
)


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    tasks: list[dict[str, object]] = []
    for tier in ("C0", "C1", "C2", "C3"):
        for category, purpose, tools, artifact_type in CATEGORIES:
            for index in range(1, 11):
                task_id = f"routing-golden-{tier.lower()}-{category}-{index:02d}"
                filename = f"{task_id}.json"
                fixture = {
                    "task_id": task_id,
                    "tier": tier,
                    "category": category,
                    "input": f"脱敏路由验收输入 {task_id}：验证 {category} 的确定性选择、故障恢复和审计关联。",
                }
                (FIXTURE_DIR / filename).write_text(
                    json.dumps(fixture, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                tasks.append(
                    {
                        "task_id": task_id,
                        "tier": tier,
                        "category": category,
                        "run_purpose": purpose,
                        "input_fixture": f"tests/fixtures/routing/{filename}",
                        "required_tools": list(tools),
                        "acceptance": {"kind": "assertion", "value": "routing_decision.status in {succeeded,failed}"},
                        "artifact_type": artifact_type,
                        "max_runtime_seconds": 120,
                    }
                )
    MANIFEST.write_text(
        json.dumps({"schema_version": 1, "manifest_id": "ibreeze-routing-golden-v1", "tasks": tasks}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
