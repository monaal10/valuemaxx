"""Dashboard tests — it must render, and the metrics it embeds must be REAL.

The dashboard hard-codes `run_metric` bodies. Nothing at import time proves those are
valid DSL, so a plausible-looking metric ships and every panel renders an error at
runtime — which is how this was almost released: `total_cost_usd / attempt_count`
reads naturally as "cost per call", but the grammar rejects it outright, because a cost
figure must never be divided by a count that includes advisory or retracted outcomes.
These tests run the embedded definitions through the same validator the API uses.
"""

from __future__ import annotations

import pytest
from _api_helpers import get, post
from fastapi.testclient import TestClient
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.api.app import build_app
from valuemaxx.api.dashboard import (
    _COST_PER_OUTCOME,  # pyright: ignore[reportPrivateUsage]
    _SPEND_BY_AGENT,  # pyright: ignore[reportPrivateUsage]
    _SPEND_BY_MODEL,  # pyright: ignore[reportPrivateUsage]
    DashboardMetric,
)
from valuemaxx.core import MetricDefinition
from valuemaxx.metrics.grammar import validate_definition

_EMBEDDED: tuple[DashboardMetric, ...] = (_SPEND_BY_MODEL, _SPEND_BY_AGENT, _COST_PER_OUTCOME)


def _client() -> TestClient:
    app = build_app(
        build_default_registry(),
        api_keys={"dev": "6f1c3b2a-0000-4a00-8000-000000000001"},
        webhook_secret=b"secret",
    )
    return TestClient(app)


@pytest.mark.parametrize("body", _EMBEDDED, ids=lambda b: b["name"])
def test_embedded_metric_is_valid_dsl(body: DashboardMetric) -> None:
    """Every metric the dashboard runs passes the real grammar validator."""
    validate_definition(
        MetricDefinition(
            name=body["name"],
            numerator=body["numerator"],
            denominator=body["denominator"],
            filters={},
            group_by=tuple(body["group_by"]),
        )
    )


@pytest.mark.parametrize("body", _EMBEDDED, ids=lambda b: b["name"])
def test_cost_metrics_use_the_billing_grade_denominator(body: DashboardMetric) -> None:
    """A cost numerator may only ever be divided by verified outcomes (H8).

    This is the product's core honesty claim rendered on screen — if the dashboard
    ever divides cost by a count that includes candidate/likely or retracted outcomes,
    it publishes an inflated number under a trustworthy-looking label.
    """
    if body["numerator"] == "total_cost_usd":
        assert body["denominator"] == "verified_outcome_count"


def test_dashboard_is_served_at_root() -> None:
    res = get(_client(), "/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<title>valuemaxx</title>" in res.text


def test_dashboard_is_self_contained() -> None:
    """No CDN, no external fetch — it must render offline and on a locked-down network."""
    body = get(_client(), "/").text.lower()
    assert "cdn." not in body
    assert "<script src=" not in body
    assert '<link rel="stylesheet"' not in body


def test_dashboard_injects_its_metric_bodies() -> None:
    """The page ships the SAME definitions Python validated — no second copy to drift."""
    body = get(_client(), "/").text
    for embedded in _EMBEDDED:
        assert f'"{embedded["name"]}"' in body
    # The placeholders must all have been substituted.
    assert "SPEND_BY_MODEL," not in body
    assert "COST_PER_OUTCOME)" not in body


def test_dashboard_does_not_shadow_a_capability_route() -> None:
    """Mounting `/` must not hide any projected capability."""
    res = post(_client(), "/capture_healthcheck", json={}, headers={"x-api-key": "dev"})
    assert res.status_code == 200
