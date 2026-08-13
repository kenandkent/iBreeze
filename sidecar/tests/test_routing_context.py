from __future__ import annotations

import pytest

from ibreeze.routing.context import build_routing_context


def test_context_normalizes_unicode_and_derives_privacy_safe_features() -> None:
    context = build_routing_context(
        run_id="run-1",
        turn_index=2,
        messages=(
            {"role": "system", "content": "Ａ"},
            {"role": "user", "content": "def f():\n    pass\nclass C:\n    pass\nreview 严格 JSON $schema properties"},
        ),
        context_window_tokens=100,
        required_capability_tags=("review", "review"),
        attachment_types=("image/png", "image/png"),
        tool_count=2,
    )
    assert context.message_char_count == len("A\ndef f():\n    pass\nclass C:\n    pass\nreview 严格 JSON $schema properties")
    assert context.contains_code is True
    assert context.contains_structured_schema is True
    assert context.contains_review_signal is True
    assert context.required_capability_tags == ("review",)
    assert context.attachment_types == ("image/png",)
    assert len(context.fingerprint()) == 64


def test_context_uses_catalog_tokenizer_and_rejects_forged_origin() -> None:
    context = build_routing_context(
        run_id="run-1",
        turn_index=1,
        messages=({"role": "user", "content": "hello"},),
        context_window_tokens=100,
        tokenizer=lambda text: 7,
    )
    assert context.estimated_input_tokens == 7
    assert context.token_estimator == "catalog_tokenizer"
    with pytest.raises(ValueError, match="ROUTING_INPUT_ORIGIN_INVALID"):
        build_routing_context(
            run_id="run-1",
            turn_index=1,
            messages=(),
            context_window_tokens=100,
            input_origin="production",
            operator_forced_mode="evaluation",
        )


def test_context_fingerprint_covers_execution_boundary_fields() -> None:
    base = dict(
        run_id="00000000-0000-0000-0000-000000000001",
        turn_index=1,
        messages=({"role": "user", "content": "hello"},),
        context_window_tokens=100,
    )
    production = build_routing_context(**base, artifact_type="code", required_capability_tags=("review",))
    evaluation = build_routing_context(
        **base,
        artifact_type="document",
        required_capability_tags=("analysis",),
        input_origin="evaluation",
    )
    assert production.fingerprint() != evaluation.fingerprint()
