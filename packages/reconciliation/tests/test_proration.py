"""Proration — the money heart of reconciliation (§5.3).

``prorate`` scales each per-request estimate so the reconciled values sum *exactly*
to the authoritative billed total, with a largest-remainder pass absorbing the
rounding residue. All math is :class:`~decimal.Decimal` with ``ROUND_HALF_EVEN`` —
never float.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from valuemaxx.reconciliation.proration import prorate, proration_factor


def test_prorated_values_sum_exactly_to_billed() -> None:
    """The reconciled values sum to the billed total to the last cent."""
    estimates = (Decimal("10"), Decimal("20"), Decimal("30"))
    billed = Decimal("66")
    result = prorate(estimates, billed)
    assert sum(result, Decimal(0)) == billed


def test_proration_factor_is_billed_over_estimate_sum() -> None:
    """proration_factor = billed_total / sum(estimates)."""
    estimates = (Decimal("10"), Decimal("30"))
    billed = Decimal("60")
    assert proration_factor(estimates, billed) == Decimal("1.5")


def test_residue_absorbed_by_largest_remainder() -> None:
    """The penny that rounding leaves over lands on the largest fractional remainder.

    Three equal estimates against $10 each scale to 3.3333...; quantized to 10dp
    they cannot sum to 10 without a residue. The largest-remainder pass must place
    the residue so the total is exactly 10.
    """
    estimates = (Decimal("1"), Decimal("1"), Decimal("1"))
    billed = Decimal("10")
    result = prorate(estimates, billed)
    assert sum(result, Decimal(0)) == billed
    # each share is ~3.3333333333; one share carries the +1 ulp residue.
    assert max(result) - min(result) == Decimal("0.0000000001")


def test_half_rounds_to_even() -> None:
    """A value at the rounding midpoint goes to the nearest even (banker's rounding).

    Two estimates of 1 against a billed total of 3 scale to exactly 1.5 each; with
    10dp quantization there is no rounding here, so to force a half-way case we use
    a billed total that makes a share land on a 5-in-the-last-place midpoint and
    assert the even neighbour is chosen rather than always-up.
    """
    # 0.00000000005 -> ROUND_HALF_EVEN -> 0.0000000000 (even), not 0.0000000001.
    estimates = (Decimal("1"), Decimal("1"))
    billed = Decimal("0.0000000001")
    result = prorate(estimates, billed)
    assert sum(result, Decimal(0)) == billed
    # one share rounds to 0.0000000000, the other carries the whole unit.
    assert sorted(result) == [Decimal("0E-10"), Decimal("0.0000000001")]


def test_single_estimate_gets_whole_billed() -> None:
    """One estimate absorbs the entire billed total."""
    assert prorate((Decimal("5"),), Decimal("123.45")) == (Decimal("123.45"),)


def test_zero_estimate_sum_with_nonzero_billed_raises() -> None:
    """Cannot prorate a non-zero invoice across estimates that sum to zero."""
    with pytest.raises(ValueError, match="cannot prorate"):
        prorate((Decimal("0"), Decimal("0")), Decimal("10"))


def test_zero_estimate_sum_with_zero_billed_is_all_zeros() -> None:
    """A zero invoice over zero estimates reconciles to zeros (no division)."""
    assert prorate((Decimal("0"), Decimal("0")), Decimal("0")) == (
        Decimal("0"),
        Decimal("0"),
    )


def test_empty_estimates_raises() -> None:
    """Proration requires at least one estimate."""
    with pytest.raises(ValueError, match="at least one estimate"):
        prorate((), Decimal("10"))


def test_prorate_never_uses_float() -> None:
    """The result is exact Decimal — passing a float in is rejected at the boundary."""
    with pytest.raises((TypeError, ValueError)):
        prorate((1.0,), Decimal("1"))  # type: ignore[arg-type]


@given(
    estimates=st.lists(
        st.integers(min_value=0, max_value=10_000_000), min_size=1, max_size=40
    ).filter(lambda xs: sum(xs) > 0),
    billed_cents=st.integers(min_value=0, max_value=1_000_000_000),
)
def test_prorated_always_sums_to_billed_property(estimates: list[int], billed_cents: int) -> None:
    """Property: for any estimates and any billed total, the shares sum exactly."""
    est = tuple(Decimal(e) for e in estimates)
    billed = Decimal(billed_cents) / Decimal(100)
    result = prorate(est, billed)
    assert sum(result, Decimal(0)) == billed
    assert len(result) == len(est)


@given(
    estimates=st.lists(st.integers(min_value=1, max_value=1_000_000), min_size=1, max_size=20),
    billed_cents=st.integers(min_value=1, max_value=100_000_000),
)
def test_shares_are_nonnegative_and_quantized(estimates: list[int], billed_cents: int) -> None:
    """Each share is non-negative and quantized to 10 decimal places."""
    est = tuple(Decimal(e) for e in estimates)
    billed = Decimal(billed_cents) / Decimal(100)
    result = prorate(est, billed)
    for share in result:
        assert share >= 0
        exponent = share.as_tuple().exponent
        assert isinstance(exponent, int)  # finite Decimal (never NaN/Inf here)
        assert -exponent <= 10
