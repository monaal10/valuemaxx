"""A curated starter pricebook so OTLP-ingested spans get real costs out of the box.

valuemaxx ships no prices by default (pricing is provider- and time-specific, and
authoritative cost should come from a gateway or the provider's billing API). But a
brand-new user wiring the SDK wants a *plausible* dollar number immediately, not
``None`` on every span. This module provides one: a snapshot of public list prices
(USD per million tokens) for the current OpenAI, Anthropic, and Google Gemini
families.

**This is an estimate, not a bill.** Prices are a point-in-time snapshot (mid-2026),
list-rate only (no negotiated/committed-use discounts, no batch/cached nuances beyond
the modeled classes). A cost computed from it carries provenance ``estimated`` — never
``measured`` or ``provider_reconciled``. Users override by passing their own
:class:`~valuemaxx.core.pricing.PriceBook`; the honesty axes make the difference
visible (an estimated cost can never be laundered into a billing-grade one).

Model ids carry version/date suffixes (``claude-3-5-haiku-20241022``). :func:`resolve_card`
matches the exact id first, then the **longest family-prefix** card, so a dated id
resolves to its family and a more specific family (``gemini-2.5-flash-lite``) is never
collapsed onto a shorter one (``gemini-2.5-flash``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache

from valuemaxx.core.enums import TokenClass
from valuemaxx.core.pricing import PriceBook, PriceCard

# The snapshot date stamped on every default card (so re-pricing later is additive).
_SNAPSHOT = datetime(2026, 1, 1, tzinfo=UTC)
_RULE_VERSION = "default-2026-01"


def _d(value: str) -> Decimal:
    return Decimal(value)


# USD per million tokens. Anthropic models price 5m/1h cache writes distinctly; OpenAI
# and Gemini model a cache-read discount but no explicit cache-write class (omitted ->
# priced at 0 with a provenance warning, never silently wrong). Output includes
# reasoning tokens at the output rate unless a provider lists a separate reasoning rate
# (none modeled here), so REASONING is intentionally not a separate key.
_CARDS: tuple[tuple[str, str, dict[TokenClass, Decimal]], ...] = (
    # --- Anthropic (input / cache_read / cache_write_5m / cache_write_1h / output) ---
    (
        "anthropic",
        "claude-3-5-haiku",
        {
            TokenClass.INPUT_UNCACHED: _d("0.80"),
            TokenClass.CACHE_READ: _d("0.08"),
            TokenClass.CACHE_WRITE_5M: _d("1.00"),
            TokenClass.CACHE_WRITE_1H: _d("1.60"),
            TokenClass.OUTPUT: _d("4.00"),
        },
    ),
    (
        "anthropic",
        "claude-3-5-sonnet",
        {
            TokenClass.INPUT_UNCACHED: _d("3.00"),
            TokenClass.CACHE_READ: _d("0.30"),
            TokenClass.CACHE_WRITE_5M: _d("3.75"),
            TokenClass.CACHE_WRITE_1H: _d("6.00"),
            TokenClass.OUTPUT: _d("15.00"),
        },
    ),
    (
        "anthropic",
        "claude-3-7-sonnet",
        {
            TokenClass.INPUT_UNCACHED: _d("3.00"),
            TokenClass.CACHE_READ: _d("0.30"),
            TokenClass.CACHE_WRITE_5M: _d("3.75"),
            TokenClass.CACHE_WRITE_1H: _d("6.00"),
            TokenClass.OUTPUT: _d("15.00"),
        },
    ),
    (
        "anthropic",
        "claude-sonnet-4",
        {
            TokenClass.INPUT_UNCACHED: _d("3.00"),
            TokenClass.CACHE_READ: _d("0.30"),
            TokenClass.CACHE_WRITE_5M: _d("3.75"),
            TokenClass.CACHE_WRITE_1H: _d("6.00"),
            TokenClass.OUTPUT: _d("15.00"),
        },
    ),
    (
        "anthropic",
        "claude-opus-4",
        {
            TokenClass.INPUT_UNCACHED: _d("15.00"),
            TokenClass.CACHE_READ: _d("1.50"),
            TokenClass.CACHE_WRITE_5M: _d("18.75"),
            TokenClass.CACHE_WRITE_1H: _d("30.00"),
            TokenClass.OUTPUT: _d("75.00"),
        },
    ),
    (
        "anthropic",
        "claude-haiku-4",
        {
            TokenClass.INPUT_UNCACHED: _d("1.00"),
            TokenClass.CACHE_READ: _d("0.10"),
            TokenClass.CACHE_WRITE_5M: _d("1.25"),
            TokenClass.CACHE_WRITE_1H: _d("2.00"),
            TokenClass.OUTPUT: _d("5.00"),
        },
    ),
    # --- OpenAI (input / cache_read / output) ---
    (
        "openai",
        "gpt-4.1",
        {
            TokenClass.INPUT_UNCACHED: _d("2.00"),
            TokenClass.CACHE_READ: _d("0.50"),
            TokenClass.OUTPUT: _d("8.00"),
        },
    ),
    (
        "openai",
        "gpt-4.1-mini",
        {
            TokenClass.INPUT_UNCACHED: _d("0.40"),
            TokenClass.CACHE_READ: _d("0.10"),
            TokenClass.OUTPUT: _d("1.60"),
        },
    ),
    (
        "openai",
        "gpt-4.1-nano",
        {
            TokenClass.INPUT_UNCACHED: _d("0.10"),
            TokenClass.CACHE_READ: _d("0.025"),
            TokenClass.OUTPUT: _d("0.40"),
        },
    ),
    (
        "openai",
        "gpt-4o",
        {
            TokenClass.INPUT_UNCACHED: _d("2.50"),
            TokenClass.CACHE_READ: _d("1.25"),
            TokenClass.OUTPUT: _d("10.00"),
        },
    ),
    (
        "openai",
        "gpt-4o-mini",
        {
            TokenClass.INPUT_UNCACHED: _d("0.15"),
            TokenClass.CACHE_READ: _d("0.075"),
            TokenClass.OUTPUT: _d("0.60"),
        },
    ),
    (
        "openai",
        "o3",
        {
            TokenClass.INPUT_UNCACHED: _d("2.00"),
            TokenClass.CACHE_READ: _d("0.50"),
            TokenClass.OUTPUT: _d("8.00"),
        },
    ),
    (
        "openai",
        "o4-mini",
        {
            TokenClass.INPUT_UNCACHED: _d("1.10"),
            TokenClass.CACHE_READ: _d("0.275"),
            TokenClass.OUTPUT: _d("4.40"),
        },
    ),
    # --- Google Gemini (input / cache_read / output) ---
    (
        "google",
        "gemini-2.5-pro",
        {
            TokenClass.INPUT_UNCACHED: _d("1.25"),
            TokenClass.CACHE_READ: _d("0.31"),
            TokenClass.OUTPUT: _d("10.00"),
        },
    ),
    (
        "google",
        "gemini-2.5-flash",
        {
            TokenClass.INPUT_UNCACHED: _d("0.30"),
            TokenClass.CACHE_READ: _d("0.075"),
            TokenClass.OUTPUT: _d("2.50"),
        },
    ),
    (
        "google",
        "gemini-2.5-flash-lite",
        {
            TokenClass.INPUT_UNCACHED: _d("0.10"),
            TokenClass.CACHE_READ: _d("0.025"),
            TokenClass.OUTPUT: _d("0.40"),
        },
    ),
    (
        "google",
        "gemini-2.0-flash",
        {
            TokenClass.INPUT_UNCACHED: _d("0.10"),
            TokenClass.CACHE_READ: _d("0.025"),
            TokenClass.OUTPUT: _d("0.40"),
        },
    ),
)


@lru_cache(maxsize=1)
def default_pricebook() -> PriceBook:
    """The curated starter :class:`PriceBook` (cached; cards are immutable)."""
    cards = tuple(
        PriceCard(
            provider=provider,
            model=model,
            usd_per_mtok=rates,
            effective_from=_SNAPSHOT,
            rule_version=_RULE_VERSION,
        )
        for provider, model, rates in _CARDS
    )
    return PriceBook(cards=cards)


def resolve_card(book: PriceBook, *, provider: str, model: str, at: datetime) -> PriceCard | None:
    """Resolve a card for ``(provider, model)`` with exact-then-family-prefix matching.

    Tries an exact ``card_for`` first. Failing that, returns the card whose model is the
    **longest prefix** of ``model`` for the same provider (so ``claude-3-5-haiku-20241022``
    resolves to the ``claude-3-5-haiku`` family, and ``gemini-2.5-flash-lite`` is never
    collapsed onto ``gemini-2.5-flash``). Returns ``None`` if nothing matches — an unknown
    model stays honestly unpriced.
    """
    exact = book.card_for(provider=provider, model=model, at=at)
    if exact is not None:
        return exact
    best: PriceCard | None = None
    for card in book.cards:
        if card.provider != provider or card.effective_from > at:
            continue
        if model.startswith(card.model) and (best is None or len(card.model) > len(best.model)):
            best = card
    return best


__all__ = ["default_pricebook", "resolve_card"]
