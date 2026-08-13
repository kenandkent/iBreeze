from __future__ import annotations

import logging

from ibreeze.logging_config import RedactionFilter
from ibreeze.observability.routing import RoutingMetrics


def test_routing_log_filter_redacts_prompt_candidate_and_credentials() -> None:
    record = logging.LogRecord(
        "ibreeze.routing",
        logging.INFO,
        __file__,
        1,
        'prompt="private input" candidate_content="model output" credential_ref="secret-ref" api_key="sk-test"',
        (),
        None,
    )
    RedactionFilter().filter(record)
    rendered = str(record.msg)
    assert "private input" not in rendered
    assert "model output" not in rendered
    assert "secret-ref" not in rendered
    assert "sk-test" not in rendered
    assert "[REDACTED]" in rendered


def test_routing_metrics_reject_prompt_and_credential_labels() -> None:
    metrics = RoutingMetrics()
    for label in ("prompt body", "credential-ref", "Authorization: Bearer token"):
        try:
            metrics.record_attempt(role="single", provider=label, model="model", status="failed")
        except ValueError:
            pass
        else:
            raise AssertionError("sensitive label was accepted")
