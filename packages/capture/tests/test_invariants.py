"""PG1 — the six token/cost invariants as lenient provenance warnings (§5.2).

``check_invariants`` is the lenient, OTLP-coerced path: it NEVER raises and NEVER
silently drops — it returns a tuple of human-readable provenance warnings for any
violated invariant, which ride on the CostEvent's ``provenance_warnings``.

``price_or_abort`` is the billing-honesty gate: when billing is genuinely
uncertain (PTU / provisioned-throughput, client-abort) it returns ``None`` cost
plus the ``billing_uncertain_abort`` warning, refusing to fabricate token x price
(H10/§13).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from valuemaxx.capture.invariants import (
    PROVISIONED_THROUGHPUT_REASON,
    check_invariants,
    price_or_abort,
)
from valuemaxx.core.enums import TokenClass
from valuemaxx.core.pricing import PriceCard
from valuemaxx.core.tokens import TokenVector

_AT = datetime(2026, 6, 27, tzinfo=UTC)


def _card() -> PriceCard:
    return PriceCard(
        provider="anthropic",
        model="claude-opus-4-8",
        usd_per_mtok={
            TokenClass.INPUT_UNCACHED: Decimal("15"),
            TokenClass.CACHE_READ: Decimal("1.5"),
            TokenClass.CACHE_WRITE_5M: Decimal("18.75"),
            TokenClass.CACHE_WRITE_1H: Decimal("30"),
            TokenClass.OUTPUT: Decimal("75"),
            TokenClass.REASONING: Decimal("75"),
        },
        effective_from=_AT,
        rule_version="v1",
    )


def test_clean_vector_no_warnings() -> None:
    """test_clean_vector_no_warnings: a well-formed vector yields no provenance warnings."""
    tokens = TokenVector(
        input_uncached=100,
        cache_read=20,
        cache_write_5m=5,
        cache_write_1h=3,
        output=50,
        reasoning=10,
    )
    assert check_invariants(tokens, provider="anthropic") == ()


def test_check_invariants_never_raises_on_pathological_input() -> None:
    """test_check_invariants_never_raises: the lenient path returns warnings, never throws."""
    # A vector that would be illegal at the strict from_provider gate cannot be
    # constructed, so we exercise the lenient checker on a borderline-but-legal one.
    tokens = TokenVector(
        input_uncached=0,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=10,
        reasoning=10,  # reasoning == output is legal (within), no warning
    )
    warnings = check_invariants(tokens, provider="anthropic")
    assert warnings == ()


def test_openai_cache_write_present_warns() -> None:
    """test_openai_cache_write_present_warns: OpenAI has no cache-write; presence is a warning."""
    tokens = TokenVector(
        input_uncached=10,
        cache_read=0,
        cache_write_5m=4,  # OpenAI does not bill cache-write -> provider-shape warning
        cache_write_1h=0,
        output=5,
        reasoning=0,
    )
    warnings = check_invariants(tokens, provider="openai")
    assert any("cache_write" in w for w in warnings)


def test_price_or_abort_normal_path_prices() -> None:
    """test_price_or_abort_normal_path_prices: a normal attempt gets a real Decimal cost."""
    tokens = TokenVector(
        input_uncached=1_000_000,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=0,
        reasoning=0,
    )
    cost, warnings = price_or_abort(
        tokens, _card(), billing_uncertain=False, provisioned_throughput=False
    )
    assert cost == Decimal("15.000000")
    assert all("billing_uncertain" not in w for w in warnings)


def test_provisioned_throughput_refuses_token_price() -> None:
    """test_provisioned_throughput_refuses_token_price: PTU -> cost_usd=None + warning (H10)."""
    tokens = TokenVector(
        input_uncached=1_000_000,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=1_000_000,
        reasoning=0,
    )
    cost, warnings = price_or_abort(
        tokens, _card(), billing_uncertain=False, provisioned_throughput=True
    )
    assert cost is None  # NEVER token x price under provisioned throughput
    assert any(PROVISIONED_THROUGHPUT_REASON in w for w in warnings)
    assert any("billing_uncertain_abort" in w for w in warnings)


def test_client_abort_refuses_token_price() -> None:
    """test_client_abort_refuses_token_price: billing_uncertain abort -> cost_usd=None + warning."""
    tokens = TokenVector(
        input_uncached=500,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=0,
        reasoning=0,
    )
    cost, warnings = price_or_abort(
        tokens, _card(), billing_uncertain=True, provisioned_throughput=False
    )
    assert cost is None
    assert any("billing_uncertain_abort" in w for w in warnings)


def test_price_or_abort_with_no_card_aborts() -> None:
    """test_price_or_abort_with_no_card_aborts: an unknown model can't be priced -> None + warn."""
    tokens = TokenVector(
        input_uncached=100,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=0,
        reasoning=0,
    )
    cost, warnings = price_or_abort(
        tokens, None, billing_uncertain=False, provisioned_throughput=False
    )
    assert cost is None
    assert any("no_price_card" in w for w in warnings)
