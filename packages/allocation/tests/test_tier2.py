"""Tier-2 shared-proportional allocation — split by declared key (§5.4)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from valuemaxx.allocation.config import SharedCostInput
from valuemaxx.allocation.tier2 import allocate_proportional, tier2_lines
from valuemaxx.core import AllocationTier, ConfidenceLabel, Provenance


def _shared(name: str, amount: str, key: str = "requests") -> SharedCostInput:
    return SharedCostInput(
        name=name,
        amount_usd=Decimal(amount),
        tier=AllocationTier.SHARED_PROPORTIONAL,
        allocation_key=key,
        rule_version="v1",
        sensitivity_pct=Decimal("5"),
    )


def test_proportional_split_sums_exactly() -> None:
    """A shared cost is split across weights so the parts sum exactly to the total."""
    weights = {"team-a": Decimal("1"), "team-b": Decimal("2"), "team-c": Decimal("3")}
    parts = allocate_proportional(Decimal("100"), weights)
    assert sum(parts.values(), Decimal(0)) == Decimal("100")


def test_lines_are_allocated_and_carry_metadata() -> None:
    """Every Tier-2 line is ALLOCATED and carries key / rule_version / confidence."""
    shared = _shared("vector-db", "300")
    weights = {"team-a": Decimal("1"), "team-b": Decimal("1")}
    lines = tier2_lines(shared, weights)
    assert len(lines) == 2
    for line in lines:
        assert line.tier is AllocationTier.SHARED_PROPORTIONAL
        assert line.label is Provenance.ALLOCATED
        assert line.allocation_key == "requests"
        assert line.rule_version == "v1"
        assert line.sensitivity_pct == Decimal("5")
        assert line.confidence is ConfidenceLabel.MEDIUM
        assert line.quarantined is False


def test_line_amounts_sum_to_shared_total() -> None:
    """The Tier-2 line amounts sum exactly to the shared cost total."""
    shared = _shared("vector-db", "300.07")
    weights = {"a": Decimal("1"), "b": Decimal("1"), "c": Decimal("1")}
    lines = tier2_lines(shared, weights)
    assert sum((line.amount_usd for line in lines), Decimal(0)) == Decimal("300.07")


def test_half_rounds_to_even() -> None:
    """The allocator rounds halves to even (banker's rounding), summing exactly."""
    weights = {"a": Decimal("1"), "b": Decimal("1")}
    parts = allocate_proportional(Decimal("0.0000000001"), weights)
    assert sum(parts.values(), Decimal(0)) == Decimal("0.0000000001")
    assert sorted(parts.values()) == [Decimal("0E-10"), Decimal("0.0000000001")]


def test_zero_weight_sum_raises() -> None:
    """Splitting a non-zero cost across zero total weight is rejected."""
    with pytest.raises(ValueError, match="zero"):
        allocate_proportional(Decimal("100"), {"a": Decimal("0"), "b": Decimal("0")})


def test_zero_total_over_zero_weight_is_all_zero() -> None:
    """A zero cost over zero weight splits to zeros (no division)."""
    parts = allocate_proportional(Decimal("0"), {"a": Decimal("0"), "b": Decimal("0")})
    assert parts == {"a": Decimal("0E-10"), "b": Decimal("0E-10")}


def test_empty_weight_map_returns_empty() -> None:
    """No consumers means an empty split."""
    assert allocate_proportional(Decimal("100"), {}) == {}


def test_non_decimal_total_rejected() -> None:
    """A float total is rejected at the boundary (money is never float)."""
    with pytest.raises(TypeError, match="never float"):
        allocate_proportional(1.0, {"a": Decimal("1")})  # type: ignore[arg-type]


def test_non_decimal_weight_rejected() -> None:
    """A float weight is rejected at the boundary (money is never float)."""
    with pytest.raises(TypeError, match="never float"):
        allocate_proportional(Decimal("1"), {"a": 1.0})  # type: ignore[dict-item]


def test_empty_weights_yields_no_lines() -> None:
    """No weights means nothing to split — no Tier-2 lines."""
    assert tier2_lines(_shared("x", "10"), {}) == ()


def test_missing_allocation_key_raises() -> None:
    """A shared input without an allocation_key cannot be split proportionally."""
    bad = SharedCostInput.model_construct(
        name="x",
        amount_usd=Decimal("10"),
        tier=AllocationTier.SHARED_PROPORTIONAL,
        allocation_key=None,
        is_idle_gpu=False,
        rule_version=None,
        sensitivity_pct=None,
    )
    with pytest.raises(ValueError, match="allocation_key"):
        tier2_lines(bad, {"a": Decimal("1")})


@given(
    weights=st.lists(st.integers(min_value=1, max_value=10_000), min_size=1, max_size=20),
    cents=st.integers(min_value=0, max_value=100_000_000),
)
def test_split_always_sums_exactly_property(weights: list[int], cents: int) -> None:
    """Property: the proportional split always sums exactly to the shared total."""
    total = Decimal(cents) / Decimal(100)
    weight_map = {f"k{i}": Decimal(w) for i, w in enumerate(weights)}
    parts = allocate_proportional(total, weight_map)
    assert sum(parts.values(), Decimal(0)) == total
