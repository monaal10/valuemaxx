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
    _OUTCOME_VOLUME,  # pyright: ignore[reportPrivateUsage]
    _SPEND_BY_AGENT,  # pyright: ignore[reportPrivateUsage]
    _SPEND_BY_MODEL,  # pyright: ignore[reportPrivateUsage]
    DashboardMetric,
)
from valuemaxx.core import MetricDefinition
from valuemaxx.metrics.grammar import validate_definition

_EMBEDDED: tuple[DashboardMetric, ...] = (
    _SPEND_BY_MODEL,
    _SPEND_BY_AGENT,
    _COST_PER_OUTCOME,
    _OUTCOME_VOLUME,
)


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


def test_dashboard_offers_an_eval_model_picker() -> None:
    """A user must be able to choose a candidate and supply their OWN key."""
    body = get(_client(), "/").text
    assert "run_eval_funnel" in body
    assert "candidate_secret_ref" in body
    assert 'id="ev-candidate"' in body


def test_eval_key_field_is_a_password_input_and_never_echoed() -> None:
    """The candidate key is a secret: masked on entry, never rendered back."""
    body = get(_client(), "/").text
    assert 'id="ev-key" type="password"' in body
    # The page must not contain any pre-filled key value.
    assert "sk-ant-" not in body


def test_dashboard_shows_outcomes_and_agents() -> None:
    """Both dimensions the user asked to see are present as panels."""
    body = get(_client(), "/").text
    assert "OUTCOMES RECORDED" in body
    assert "SPEND BY AGENT" in body


def test_dashboard_shows_what_switching_would_cost() -> None:
    """The one sentence a user wants: "switch and save X%".

    A recommendation used to say only that a candidate holds parity. Showing the
    projected cost beside it is what turns "it's as good" into a decision.
    """
    body = get(_client(), "/").text
    assert "estimate_switch_cost" in body
    assert 'id="ev-savings"' in body


def test_the_switch_estimate_is_labelled_estimated() -> None:
    """It is list price applied to traffic the candidate never served.

    Rendering it as a billed number would be exactly the provenance laundering the
    honesty axes exist to prevent.
    """
    body = get(_client(), "/").text
    assert "not billed" in body


def test_the_page_leads_with_outcomes_not_spend() -> None:
    """Cost-per-outcome must appear ABOVE spend-by-model on the page.

    Ordering is the positioning. A page whose first table is provider spend reads as
    a cost dashboard — the commoditized half that Helicone and Langfuse already show
    — and buries the one number nobody else has. The differentiator has to be the
    thing a stranger sees first.
    """
    body = get(_client(), "/").text

    assert body.index("COST PER OUTCOME") < body.index("SPEND BY MODEL")
    assert body.index("COST PER OUTCOME") < body.index("SPEND BY AGENT")


def test_every_honesty_field_the_executor_returns_is_rendered() -> None:
    """A cell carries four honesty signals; the page must not silently drop three.

    `minimum_tier` was already rendered. The other three are exactly what Phase A
    added or surfaced, and each answers a question a buyer asks about the headline
    number: was this OBSERVED or inferred (causal_evidence), is this cost split with
    another outcome (shared_attribution_count), and what was excluded from the
    denominator to get here (advisory_excluded_count). Computing them and then
    dropping them at the last step forfeits the whole differentiator.
    """
    body = get(_client(), "/").text

    for field in ("causal_evidence", "shared_attribution_count", "advisory_excluded_count"):
        assert field in body, f"dashboard never reads {field}"


def test_unattributed_spend_is_a_visible_row_not_an_omission() -> None:
    """A user who sees "7% unattributed, here's why" trusts the other 93%.

    Quietly dropping the spend that joined to no outcome makes every remaining number
    look more complete than it is — the failure mode the tier system exists to
    prevent, reintroduced at the render layer.
    """
    body = get(_client(), "/").text

    assert "unattributed" in body.lower()


def test_an_absent_number_is_never_escaped_into_literal_text() -> None:
    """A missing cost must render as an em-dash, not the characters "&amp;mdash;".

    `esc("&mdash;")` escapes the ampersand, so the fallback for an absent value was
    printed to the page verbatim. It is cosmetic until you remember what the blank
    means: "no data yet" is a different fact from zero, and a cell that renders
    garbage where it should say "unknown" undermines exactly that distinction.
    """
    body = get(_client(), "/").text
    js = body.split("<script>")[1].split("</script>")[0]

    assert 'esc(c.numerator_value ?? "&mdash;")' not in js
    assert 'esc(c.denominator_value ?? "&mdash;")' not in js
    assert "const num = (v) =>" in js


def test_the_page_exposes_competing_attributions_for_one_outcome() -> None:
    """The T4 resolver returns candidate SETS; the page must be able to show them.

    When several runs could have produced an outcome the cascade halts rather than
    picking one, and the losing candidates — each with a score and a rationale — are
    the evidence behind a `candidate`-tier number. Computing them and never offering
    a way to look means "why is this only candidate-tier?" has no answer on the page.
    """
    body = get(_client(), "/").text

    assert "list_review_queue" in body
    # The competing runs and WHY each was scored that way, not just the winner.
    assert "rationale" in body
    assert "candidates" in body


def test_cost_is_decomposable_by_agent_and_model() -> None:
    """"Which part of achieving this outcome is expensive" must be answerable.

    Cost per outcome grouped by agent and by model is the bridge to optimization:
    a single blended figure says a unit costs $0.10 but never which step to attack.
    """
    body = get(_client(), "/").text

    assert "SPEND BY AGENT" in body
    assert "SPEND BY MODEL" in body


def test_insufficient_data_is_a_named_state_not_a_bare_dash() -> None:
    """Spend with no billing-grade outcome yet must SAY so, not show an em-dash.

    The executor returns `value: null` when the denominator is zero — it refuses to
    publish a fabricated ratio, which is right. But a row rendering "— | $12.40 | 0"
    is indistinguishable from a broken cell, so the user cannot tell "we spent money
    and nothing has bound yet" from "this panel is malfunctioning". The first is a
    real, actionable state; treating it as a rendering gap wastes the honesty the
    null was protecting.
    """
    body = get(_client(), "/").text

    assert "insufficient data" in body.lower()
