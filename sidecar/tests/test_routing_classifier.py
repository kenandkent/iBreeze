from __future__ import annotations

from ibreeze.routing.classifier import RulesV1Classifier
from ibreeze.routing.context import build_routing_context


def _context(**kwargs):
    defaults = {
        "run_id": "run-1",
        "turn_index": 1,
        "messages": ({"role": "user", "content": "hello"},),
        "context_window_tokens": 10000,
    }
    defaults.update(kwargs)
    return build_routing_context(**defaults)


def test_rules_v1_boundaries_and_cap() -> None:
    classifier = RulesV1Classifier()
    assert classifier.classify(_context(run_purpose="repair")).required_tier == "C3"
    assert classifier.classify(_context(verification_failures=1)).required_tier == "C3"
    assert classifier.classify(_context(provider_failures=2)).required_tier == "C1"
    assert classifier.classify(_context(context_window_tokens=100, messages=({"role": "user", "content": "x" * 4000},))).required_tier in {"C1", "C2", "C3"}
