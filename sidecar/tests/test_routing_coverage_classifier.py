from __future__ import annotations

from ibreeze.routing.classifier import RulesV1Classifier, classify
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


def test_code_review_and_schema_signals() -> None:
    classifier = RulesV1Classifier()
    decision = classifier.classify(
        _context(messages=({"role": "user", "content": "```python\nx = 1\n```\nplease review"},))
    )
    assert "code_review_or_verification" in decision.rules
    decision = classifier.classify(
        _context(messages=({"role": "user", "content": '{"$schema": "https://x", "properties": {}}'},))
    )
    assert "structured_schema" in decision.rules


def test_workflow_review_purposes() -> None:
    classifier = RulesV1Classifier()
    for purpose in ("company_plan", "review", "verification", "summary"):
        decision = classifier.classify(_context(run_purpose=purpose))
        assert "workflow_review" in decision.rules


def test_failure_history_capped_when_already_c3() -> None:
    classifier = RulesV1Classifier()
    decision = classifier.classify(_context(run_purpose="repair", provider_failures=2))
    assert "failure_history_capped" in decision.rules


def test_open_blocker_high_raises_tier() -> None:
    classifier = RulesV1Classifier()
    decision = classifier.classify(_context(open_blocker_high_count=1))
    assert "open_blocker_high" in decision.rules
    assert decision.required_tier == "C3"


def test_module_level_classify_wrapper() -> None:
    decision = classify(_context(run_purpose="merge"))
    assert decision.required_tier == "C3"
