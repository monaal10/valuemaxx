"""G1-CORE-CAPTURE-FIELDS: PriceCard + PriceBook — per-provider per-class pricing."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from valuemaxx.core.enums import TokenClass
from valuemaxx.core.pricing import PriceBook, PriceCard


def _anthropic_card(effective_from: datetime, rule_version: str) -> PriceCard:
    # Anthropic prices all six classes, incl distinct 5m/1h cache writes.
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
        effective_from=effective_from,
        rule_version=rule_version,
    )


def _openai_card() -> PriceCard:
    # OpenAI has a cache-read discount but NO explicit cache-write price.
    return PriceCard(
        provider="openai",
        model="gpt-5",
        usd_per_mtok={
            TokenClass.INPUT_UNCACHED: Decimal("10"),
            TokenClass.CACHE_READ: Decimal("2.5"),
            TokenClass.OUTPUT: Decimal("30"),
        },
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        rule_version="v1",
    )


def test_price_card_per_token_class() -> None:
    """test_price_card_per_token_class: a card prices each token class distinctly."""
    card = _anthropic_card(datetime(2026, 1, 1, tzinfo=UTC), "v1")
    write_5m = card.usd_per_mtok[TokenClass.CACHE_WRITE_5M]
    write_1h = card.usd_per_mtok[TokenClass.CACHE_WRITE_1H]
    assert write_5m == Decimal("18.75")
    assert write_1h == Decimal("30")
    assert write_5m != write_1h  # distinct 5m/1h cache-write prices


def test_openai_no_cache_write_price_modeled() -> None:
    """test_openai_no_cache_write_price_modeled: OpenAI card simply omits cache-write."""
    card = _openai_card()
    assert TokenClass.CACHE_WRITE_5M not in card.usd_per_mtok
    assert TokenClass.CACHE_WRITE_1H not in card.usd_per_mtok
    assert card.usd_per_mtok[TokenClass.CACHE_READ] == Decimal("2.5")


def test_pricebook_picks_effective_card_by_date() -> None:
    """test_pricebook_picks_effective_card_by_date: card_for returns the latest effective card."""
    old = _anthropic_card(datetime(2026, 1, 1, tzinfo=UTC), "v1")
    new = _anthropic_card(datetime(2026, 6, 1, tzinfo=UTC), "v2")
    book = PriceBook(cards=(old, new))
    picked = book.card_for(
        provider="anthropic", model="claude-opus-4-8", at=datetime(2026, 6, 15, tzinfo=UTC)
    )
    assert picked is not None
    assert picked.rule_version == "v2"
    # before the new card's effective date, the old card applies
    picked_old = book.card_for(
        provider="anthropic", model="claude-opus-4-8", at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    assert picked_old is not None
    assert picked_old.rule_version == "v1"


def test_pricebook_returns_none_when_no_card() -> None:
    book = PriceBook(cards=(_openai_card(),))
    assert (
        book.card_for(provider="anthropic", model="x", at=datetime(2026, 6, 1, tzinfo=UTC)) is None
    )


def test_pricebook_returns_none_before_any_effective_date() -> None:
    book = PriceBook(cards=(_openai_card(),))
    picked = book.card_for(provider="openai", model="gpt-5", at=datetime(2025, 1, 1, tzinfo=UTC))
    assert picked is None
