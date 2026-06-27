"""PG1 — per-token-class cost math (§5.2). Money is Decimal, never float (M7).

``compute_cost_usd`` prices each of the six token classes from a
:class:`~valuemaxx.core.pricing.PriceCard`, summing in :class:`~decimal.Decimal`
and quantizing the total to ``0.000001`` with ``ROUND_HALF_EVEN`` (banker's
rounding). Pricing is provider-specific: a class the card omits (e.g. OpenAI's
cache-write) prices to **zero** and records a provenance warning — we never crash
on a missing price and never silently price a class we don't have a rate for.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING

from valuemaxx.core.enums import TokenClass

if TYPE_CHECKING:
    from valuemaxx.core.pricing import PriceCard
    from valuemaxx.core.tokens import TokenVector

_QUANTUM = Decimal("0.000001")
_PER_MILLION = Decimal("1000000")

# The vector field name carrying each token class's count.
_CLASS_FIELDS: tuple[tuple[TokenClass, str], ...] = (
    (TokenClass.INPUT_UNCACHED, "input_uncached"),
    (TokenClass.CACHE_READ, "cache_read"),
    (TokenClass.CACHE_WRITE_5M, "cache_write_5m"),
    (TokenClass.CACHE_WRITE_1H, "cache_write_1h"),
    (TokenClass.OUTPUT, "output"),
    (TokenClass.REASONING, "reasoning"),
)


def compute_cost_usd(tokens: TokenVector, card: PriceCard) -> tuple[Decimal, tuple[str, ...]]:
    """Price a token vector against a card; return (cost_usd, provenance_warnings).

    Cost = sum over classes of ``(count / 1_000_000) * usd_per_mtok[class]``,
    summed in :class:`~decimal.Decimal` and quantized to ``0.000001`` with
    ``ROUND_HALF_EVEN``. A non-zero count for a class the card does not price is
    treated as ``$0`` for that class and produces a warning naming the class — the
    cost is honest about what it could and could not price, never silent.
    """
    total = Decimal("0")
    warnings: list[str] = []
    for token_class, field in _CLASS_FIELDS:
        count = getattr(tokens, field)
        if count == 0:
            continue
        rate = card.usd_per_mtok.get(token_class)
        if rate is None:
            warnings.append(
                f"unpriced_token_class: {field} has {count} tokens but "
                f"{card.provider}/{card.model} card has no {token_class.value} rate (priced $0)"
            )
            continue
        total += (Decimal(count) / _PER_MILLION) * rate
    return total.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN), tuple(warnings)


__all__ = ["compute_cost_usd"]
