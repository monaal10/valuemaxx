"""PG1 — per-token-class cost math (§5.2): Decimal ROUND_HALF_EVEN, never float.

``compute_cost_usd`` prices each token class from a :class:`PriceCard`, sums in
:class:`~decimal.Decimal` (money is never ``float``, M7), and quantizes to
``0.000001`` with ``ROUND_HALF_EVEN``. A token class the card omits (e.g. OpenAI
cache-write) prices to zero AND records a provenance warning — never silently
priced and never crashed.

``billing_uncertain`` (PTU / client-abort) returns ``None`` cost with a warning —
we refuse to publish a fabricated token x price number (H10/§13).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.capture.pricing import compute_cost_usd
from valuemaxx.core.enums import TokenClass
from valuemaxx.core.pricing import PriceCard
from valuemaxx.core.tokens import TokenVector

if TYPE_CHECKING:
    import pytest

_AT = datetime(2026, 6, 27, tzinfo=UTC)


def _anthropic_card() -> PriceCard:
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


def _openai_card() -> PriceCard:
    return PriceCard(
        provider="openai",
        model="gpt-5",
        usd_per_mtok={
            TokenClass.INPUT_UNCACHED: Decimal("10"),
            TokenClass.CACHE_READ: Decimal("2.5"),
            TokenClass.OUTPUT: Decimal("30"),
        },
        effective_from=_AT,
        rule_version="v1",
    )


def test_cost_sums_per_class_in_decimal() -> None:
    """test_cost_sums_per_class_in_decimal: cost = sum (tokens/1e6 * usd_per_mtok), Decimal."""
    tokens = TokenVector(
        input_uncached=1_000_000,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=1_000_000,
        reasoning=0,
    )
    cost, warnings = compute_cost_usd(tokens, _anthropic_card())
    # 1M input @ $15/M + 1M output @ $75/M = $90.000000
    assert cost == Decimal("90.000000")
    assert isinstance(cost, Decimal)
    assert warnings == ()


def test_reasoning_not_double_charged_beyond_output() -> None:
    """test_reasoning_not_double_charged_beyond_output: reasoning is priced as its own class.

    reasoning is embedded within output but priced at the reasoning rate; the
    output class is the non-reasoning remainder is NOT modelled here — both classes
    are summed from the vector's explicit counts (the vector already split them).
    """
    tokens = TokenVector(
        input_uncached=0,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=100,
        reasoning=40,
    )
    cost, _warnings = compute_cost_usd(tokens, _anthropic_card())
    # 100 output @75/M + 40 reasoning @75/M = (140/1e6)*75
    assert cost == Decimal("0.010500")


def test_quantize_is_round_half_even() -> None:
    """test_quantize_is_round_half_even: banker's rounding at 1e-6, not half-up."""
    # craft a raw value that lands exactly on a half at the 7th decimal so rounding
    # direction is observable: 1 token @ $0.0000005/M-ish. Use 5 tokens of a class
    # priced to produce ...5 at the 7th place.
    card = PriceCard(
        provider="x",
        model="y",
        usd_per_mtok={TokenClass.OUTPUT: Decimal("0.5")},
        effective_from=_AT,
        rule_version="v1",
    )
    # 1 token @ 0.5/M = 0.0000005 -> quantize to 1e-6 half-even -> 0.000000 (round to even)
    tokens = TokenVector(
        input_uncached=0,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=1,
        reasoning=0,
    )
    cost, _ = compute_cost_usd(tokens, card)
    assert cost == Decimal("0.000000")
    # 3 tokens @ 0.5/M = 0.0000015 -> half-even rounds to 0.000002 (2 is even)
    tokens3 = TokenVector(
        input_uncached=0,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=3,
        reasoning=0,
    )
    cost3, _ = compute_cost_usd(tokens3, card)
    assert cost3 == Decimal("0.000002")


def test_openai_cache_write_priced_zero_with_warning() -> None:
    """test_openai_cache_write_priced_zero_with_warning: an omitted class is $0 + a warning."""
    tokens = TokenVector(
        input_uncached=0,
        cache_read=0,
        cache_write_5m=1_000_000,  # OpenAI card has no cache-write price
        cache_write_1h=0,
        output=0,
        reasoning=0,
    )
    cost, warnings = compute_cost_usd(tokens, _openai_card())
    assert cost == Decimal("0.000000")  # priced zero, never crashed
    assert any("cache_write_5m" in w for w in warnings)


def test_never_uses_float_internally(monkeypatch: pytest.MonkeyPatch) -> None:
    """test_never_uses_float_internally: monkeypatch float to raise; cost math still works."""

    def _boom(*_args: object, **_kwargs: object) -> float:
        raise AssertionError("float() must never be used in cost math (money is Decimal)")

    monkeypatch.setattr("builtins.float", _boom)
    tokens = TokenVector(
        input_uncached=123_456,
        cache_read=7_890,
        cache_write_5m=100,
        cache_write_1h=50,
        output=4_321,
        reasoning=10,
    )
    cost, _ = compute_cost_usd(tokens, _anthropic_card())
    assert isinstance(cost, Decimal)


def test_zero_tokens_zero_cost() -> None:
    tokens = TokenVector(
        input_uncached=0, cache_read=0, cache_write_5m=0, cache_write_1h=0, output=0, reasoning=0
    )
    cost, warnings = compute_cost_usd(tokens, _anthropic_card())
    assert cost == Decimal("0.000000")
    assert warnings == ()
