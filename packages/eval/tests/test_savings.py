"""What switching a model would cost — the half a recommendation never carried.

An eval could say "this candidate holds parity" and never "…and it is 92% cheaper per
outcome". These tests pin the properties that make that percentage trustworthy: it is
computed from the tenant's OWN observed token mix (not a headline rate ratio), an
unpriceable model produces no number rather than a fake zero, and a zero baseline
yields None instead of a fabricated infinity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from valuemaxx.capture.pricing import compute_cost_usd
from valuemaxx.core import CostEvent, ProvenanceLabel
from valuemaxx.core.enums import CaptureGranularity, Provenance, TokenClass
from valuemaxx.core.ids import AttemptId, CostEventId, RunId, TenantId
from valuemaxx.core.pricing import PriceBook, PriceCard
from valuemaxx.core.tokens import TokenVector
from valuemaxx.eval.savings import estimate_switch

_TENANT = TenantId(UUID("6f1c3b2a-0000-4a00-8000-000000000001"))
_NOW = datetime(2026, 7, 31, tzinfo=UTC)


def _card(model: str, *, inp: str, out: str) -> PriceCard:
    return PriceCard(
        provider="anthropic",
        model=model,
        usd_per_mtok={
            TokenClass.INPUT_UNCACHED: Decimal(inp),
            TokenClass.CACHE_READ: Decimal("0"),
            TokenClass.CACHE_WRITE_5M: Decimal("0"),
            TokenClass.CACHE_WRITE_1H: Decimal("0"),
            TokenClass.OUTPUT: Decimal(out),
        },
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        rule_version="test",
    )


_BOOK = PriceBook(cards=(_card("cheap", inp="1", out="2"),))


# The REAL pricer from `valuemaxx.capture`. The eval package may not import it (the
# logic packages are independent), but a test can — and using the production
# arithmetic here means these numbers are the ones a user would actually see.
_price = compute_cost_usd


def _event(model: str, *, cost: str | None, inp: int = 1_000_000, out: int = 0) -> CostEvent:

    return CostEvent(
        tenant_id=_TENANT,
        id=CostEventId("ce_1"),
        run_id=RunId("r1"),
        attempt_id=AttemptId("a1"),
        provider="anthropic",
        model=model,
        tokens=TokenVector(
            input_uncached=inp,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=out,
            reasoning=0,
        ),
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(
            provenance=Provenance.ESTIMATED, reconciliation_record_id=None, note=None
        ),
        cost_usd=None if cost is None else Decimal(cost),
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=False,
        provenance_warnings=(),
        occurred_at=_NOW,
    )


def test_reprices_the_incumbents_own_traffic() -> None:
    """1M input tokens at $1/Mtok = $1 on the candidate, vs $10 actually spent."""
    result = estimate_switch(
        [_event("pricey", cost="10")],
        incumbent_model="pricey",
        candidate_model="cheap",
        candidate_provider="anthropic",
        pricebook=_BOOK,
        price=_price,
        at=_NOW,
    )
    estimate = result.estimate
    assert estimate is not None
    assert estimate.incumbent_usd == Decimal("10")
    assert estimate.candidate_usd == Decimal("1")
    assert estimate.delta_usd == Decimal("-9")
    assert estimate.pct_change == Decimal("-90")


def test_only_the_incumbents_events_are_repriced() -> None:
    """Repricing another model's traffic would answer a question nobody asked."""
    result = estimate_switch(
        [_event("pricey", cost="10"), _event("something-else", cost="99")],
        incumbent_model="pricey",
        candidate_model="cheap",
        candidate_provider="anthropic",
        pricebook=_BOOK,
        price=_price,
        at=_NOW,
    )
    assert result.estimate is not None
    assert result.estimate.incumbent_usd == Decimal("10")
    assert result.estimate.event_count == 1


def test_an_unpriceable_candidate_returns_no_number_not_a_zero() -> None:
    """A missing card as $0 would report a 100% saving for a model we cannot price."""
    result = estimate_switch(
        [_event("pricey", cost="10")],
        incumbent_model="pricey",
        candidate_model="model-we-have-no-card-for",
        candidate_provider="anthropic",
        pricebook=_BOOK,
        price=_price,
        at=_NOW,
    )
    assert result.estimate is None
    assert result.reason is not None
    assert "no price card" in result.reason


def test_no_incumbent_traffic_says_so() -> None:
    result = estimate_switch(
        [],
        incumbent_model="pricey",
        candidate_model="cheap",
        candidate_provider="anthropic",
        pricebook=_BOOK,
        price=_price,
        at=_NOW,
    )
    assert result.estimate is None
    assert result.reason is not None
    assert "no captured traffic" in result.reason


def test_unpriced_incumbent_events_are_not_counted_as_free() -> None:
    """Treating an unpriced event as $0 would understate what the tenant spends today."""
    result = estimate_switch(
        [_event("pricey", cost=None)],
        incumbent_model="pricey",
        candidate_model="cheap",
        candidate_provider="anthropic",
        pricebook=_BOOK,
        price=_price,
        at=_NOW,
    )
    assert result.estimate is None
    assert result.reason is not None
    assert "carry no cost" in result.reason


def test_a_zero_baseline_yields_no_percentage() -> None:
    """ "100% cheaper than free" is not a claim worth making — and dividing would crash."""
    result = estimate_switch(
        [_event("pricey", cost="0")],
        incumbent_model="pricey",
        candidate_model="cheap",
        candidate_provider="anthropic",
        pricebook=_BOOK,
        price=_price,
        at=_NOW,
    )
    assert result.estimate is not None
    assert result.estimate.pct_change is None
