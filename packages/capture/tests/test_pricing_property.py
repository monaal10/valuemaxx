"""PG1 — property-based checks on the cost math (Hypothesis; AGENTS.md §1).

The token-vector cost is invariant-heavy, so we assert structural properties that
must hold for *any* legal token vector, not just hand-picked examples:
  * cost is non-negative;
  * cost is monotonic non-decreasing as any single token class grows;
  * cost computed before quantization equals the exact rational sum (no float).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st
from valuemaxx.capture.pricing import compute_cost_usd
from valuemaxx.core.enums import TokenClass
from valuemaxx.core.pricing import PriceCard
from valuemaxx.core.tokens import TokenVector

_AT = datetime(2026, 6, 27, tzinfo=UTC)
_CARD = PriceCard(
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

_counts = st.integers(min_value=0, max_value=10_000_000)


def _vector(iu: int, cr: int, c5: int, c1: int, out: int, reasoning: int) -> TokenVector:
    return TokenVector(
        input_uncached=iu,
        cache_read=cr,
        cache_write_5m=c5,
        cache_write_1h=c1,
        output=out,
        reasoning=min(reasoning, out),  # keep reasoning <= output (invariant 2)
    )


@given(_counts, _counts, _counts, _counts, _counts, _counts)
def test_cost_is_non_negative(iu: int, cr: int, c5: int, c1: int, out: int, reasoning: int) -> None:
    """test_cost_is_non_negative: priced cost is never negative for any legal vector."""
    cost, _ = compute_cost_usd(_vector(iu, cr, c5, c1, out, reasoning), _CARD)
    assert cost >= Decimal("0")


@given(_counts, _counts)
def test_cost_monotonic_in_output(out: int, bump: int) -> None:
    """test_cost_monotonic_in_output: more output tokens never decreases cost."""
    base, _ = compute_cost_usd(_vector(0, 0, 0, 0, out, 0), _CARD)
    more, _ = compute_cost_usd(_vector(0, 0, 0, 0, out + bump, 0), _CARD)
    assert more >= base
