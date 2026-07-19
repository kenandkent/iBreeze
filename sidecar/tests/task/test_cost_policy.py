"""test_cost_policy：稳定性降级链 + 角色档位（P9-T9）。"""

from __future__ import annotations

import pytest

from acos.task.cost_policy import CostPolicy, decide_degrade


def test_low_stability_direct_human():
    d = decide_degrade(stability_level=2, attempt=1, current_tier="standard",
                       dept_employees=["e1", "e2"], current_employee_id="e1")
    assert d.action == "human"


def test_high_stability_retry_same_tier_first():
    d = decide_degrade(stability_level=8, attempt=1, current_tier="standard",
                       dept_employees=["e1", "e2"], current_employee_id="e1")
    assert d.action == "retry_same_tier"


def test_high_stability_upgrade_tier():
    d = decide_degrade(stability_level=8, attempt=2, current_tier="free",
                       dept_employees=["e1", "e2"], current_employee_id="e1")
    assert d.action == "upgrade_tier"
    assert d.next_tier == "standard"


def test_high_stability_upgrade_ceiling_then_human():
    d = decide_degrade(stability_level=8, attempt=2, current_tier="premium",
                       dept_employees=["e1", "e2"], current_employee_id="e1")
    assert d.action == "human"


def test_mid_stability_reassign():
    d = decide_degrade(stability_level=5, attempt=2, current_tier="standard",
                       dept_employees=["e1", "e2"], current_employee_id="e1")
    assert d.action == "reassign"
    assert d.next_employee_id == "e2"


def test_mid_stability_escalate_when_no_others():
    d = decide_degrade(stability_level=5, attempt=2, current_tier="standard",
                       dept_employees=["e1"], current_employee_id="e1")
    assert d.action == "escalate_manager"


def test_tier_for_role():
    assert CostPolicy.tier_for_role("manager") == "premium"
    assert CostPolicy.tier_for_role("worker", stability_level=2) == "free"
    assert CostPolicy.tier_for_role("worker", stability_level=6) == "standard"
    assert CostPolicy.worker_upgrade_ceiling() == "premium"


def test_mid_stability_retry_first():
    d = decide_degrade(stability_level=5, attempt=1, current_tier="standard",
                       dept_employees=["e1", "e2"], current_employee_id="e1")
    assert d.action == "retry_same_tier"


def test_high_stability_second_attempt_ceiling_free():
    d = decide_degrade(stability_level=8, attempt=2, current_tier="free",
                       dept_employees=["e1"], current_employee_id="e1")
    assert d.action == "upgrade_tier"
    assert d.next_tier == "standard"
