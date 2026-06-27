"""Pricing — per-provider, per-token-class price cards (§5.2).

Pricing is provider-specific: Anthropic prices distinct 5m/1h cache writes while
OpenAI has a cache-read discount but no explicit cache-write price (its card simply
omits those classes). A :class:`PriceBook` selects the card in effect at a given
time, so a re-priced model doesn't retroactively change historical cost.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from valuemaxx.core.base import StrictModel
from valuemaxx.core.enums import TokenClass


class PriceCard(StrictModel):
    """The price (USD per million tokens) for each token class of one model."""

    provider: str
    model: str
    usd_per_mtok: Mapping[TokenClass, Decimal]
    effective_from: datetime
    rule_version: str


class PriceBook(StrictModel):
    """A collection of price cards with effective-date selection."""

    cards: tuple[PriceCard, ...]

    def card_for(self, *, provider: str, model: str, at: datetime) -> PriceCard | None:
        """Return the card for (provider, model) in effect at ``at``, or None.

        Picks the card with the latest ``effective_from`` that is not after ``at``.
        """
        candidates = [
            card
            for card in self.cards
            if card.provider == provider and card.model == model and card.effective_from <= at
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda card: card.effective_from)


__all__ = ["PriceBook", "PriceCard"]
