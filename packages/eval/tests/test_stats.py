"""FOUNDATION: pure statistics for the eval funnel (closed-form, deterministic)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from valuemaxx.eval.stats import (
    ci_separated,
    meets_hysteresis,
    non_inferiority,
    percentiles,
    relative_improvement,
    required_sample_size,
    underperforms_by,
    wilson_ci,
)

# ---------------------------------------------------------------- wilson_ci


def test_wilson_ci_zero_successes_lower_is_zero() -> None:
    """0/n successes: the lower bound is 0 and the interval is degenerate at the low end."""
    low, high = wilson_ci(successes=0, n=20)
    assert low == pytest.approx(0.0, abs=1e-9)
    assert 0.0 < high < 0.25


def test_wilson_ci_all_successes_upper_is_one() -> None:
    """n/n successes: the upper bound is 1.0 (the Wilson interval never exceeds [0, 1])."""
    low, high = wilson_ci(successes=20, n=20)
    assert high == pytest.approx(1.0, abs=1e-9)
    assert 0.75 < low < 1.0


def test_wilson_ci_known_value_half() -> None:
    """A well-known textbook value: 50/100 at 95% gives ~[0.404, 0.596]."""
    low, high = wilson_ci(successes=50, n=100)
    assert low == pytest.approx(0.4038, abs=1e-3)
    assert high == pytest.approx(0.5962, abs=1e-3)


def test_wilson_ci_centered_inside_interval() -> None:
    """The point estimate p lies within (low, high) for an interior proportion."""
    low, high = wilson_ci(successes=30, n=50)
    p = 30 / 50
    assert low < p < high


def test_wilson_ci_n_zero_raises() -> None:
    """An empty sample has no interval — it raises rather than dividing by zero."""
    with pytest.raises(ValueError, match="n must be positive"):
        wilson_ci(successes=0, n=0)


def test_wilson_ci_successes_exceeds_n_raises() -> None:
    """More successes than trials is impossible — rejected at the boundary."""
    with pytest.raises(ValueError, match="successes"):
        wilson_ci(successes=11, n=10)


@given(
    n=st.integers(min_value=1, max_value=2000),
    frac=st.floats(min_value=0.0, max_value=1.0),
)
def test_wilson_ci_always_within_unit_and_ordered(n: int, frac: float) -> None:
    """Property: the interval is always inside [0, 1] and low <= high."""
    successes = round(frac * n)
    low, high = wilson_ci(successes=successes, n=n)
    assert 0.0 <= low <= high <= 1.0


# ---------------------------------------------------------------- percentiles


def test_percentiles_returns_p50_p95_p99() -> None:
    """percentiles returns the three named latency quantiles, in order."""
    samples = [float(x) for x in range(1, 101)]  # 1..100
    p = percentiles(samples)
    assert p.p50 < p.p95 < p.p99


def test_percentiles_single_value_collapses() -> None:
    """A single sample makes all three percentiles equal that value."""
    p = percentiles([42.0])
    assert p.p50 == p.p95 == p.p99 == 42.0


def test_percentiles_monotone_non_decreasing() -> None:
    """p50 <= p95 <= p99 always (a percentile vector is monotone)."""
    p = percentiles([10.0, 20.0, 30.0, 40.0, 50.0])
    assert p.p50 <= p.p95 <= p.p99


def test_percentiles_empty_raises() -> None:
    """An empty latency sample has no percentiles — it raises."""
    with pytest.raises(ValueError, match="at least one sample"):
        percentiles([])


def test_percentiles_unsorted_input_handled() -> None:
    """The input need not be pre-sorted; the percentile is order-independent."""
    p_sorted = percentiles([1.0, 2.0, 3.0, 4.0])
    p_shuffled = percentiles([3.0, 1.0, 4.0, 2.0])
    assert p_sorted == p_shuffled


# ---------------------------------------------------------------- ci_separated


def test_ci_separated_true_when_disjoint() -> None:
    """Two non-overlapping intervals are separated."""
    assert ci_separated((0.80, 0.90), (0.60, 0.70)) is True


def test_ci_separated_false_when_overlapping() -> None:
    """Overlapping intervals are not separated (the deltas are not significant)."""
    assert ci_separated((0.70, 0.85), (0.60, 0.75)) is False


def test_ci_separated_false_when_touching() -> None:
    """Intervals that merely touch at an endpoint are NOT separated (strict)."""
    assert ci_separated((0.70, 0.80), (0.60, 0.70)) is False


def test_ci_separated_order_independent() -> None:
    """Separation does not depend on which interval is passed first."""
    assert ci_separated((0.60, 0.70), (0.80, 0.90)) is True


# ---------------------------------------------------------------- relative_improvement


def test_relative_improvement_basic() -> None:
    """(new - old) / |old| — a 0.6 -> 0.75 lift is +0.25."""
    assert relative_improvement(new=0.75, old=0.60) == pytest.approx(0.25)


def test_relative_improvement_zero_zero_is_zero() -> None:
    """relative_improvement(0, 0) == 0 (no baseline, no change — never NaN/inf)."""
    assert relative_improvement(new=0.0, old=0.0) == 0.0


def test_relative_improvement_negative_when_worse() -> None:
    """A regression yields a negative relative improvement."""
    assert relative_improvement(new=0.50, old=0.60) == pytest.approx(-1 / 6)


def test_relative_improvement_uses_absolute_baseline() -> None:
    """The denominator is |old|, so a negative baseline still gives a sane sign."""
    assert math.isfinite(relative_improvement(new=-0.5, old=-1.0))


# ---------------------------------------------------------------- meets_hysteresis


def test_meets_hysteresis_at_threshold_passes() -> None:
    """Exactly 15% relative change meets the >=0.15 switching hysteresis."""
    assert meets_hysteresis(new=1.15, old=1.0) is True


def test_meets_hysteresis_just_below_blocks() -> None:
    """14.9% relative change does not meet the hysteresis — churn is blocked."""
    assert meets_hysteresis(new=1.149, old=1.0) is False


def test_meets_hysteresis_symmetric_on_decrease() -> None:
    """A 15% decrease also meets the hysteresis (|new-old|/|old|)."""
    assert meets_hysteresis(new=0.85, old=1.0) is True


# ---------------------------------------------------------------- underperforms_by


def test_underperforms_by_more_than_25_percent() -> None:
    """A candidate 30% below the incumbent underperforms (eliminated at smoke)."""
    assert underperforms_by(candidate=0.70, incumbent=1.0, fraction=0.25) is True


def test_underperforms_exactly_25_percent_is_strict() -> None:
    """At exactly 25% below, the candidate is NOT eliminated (strict ``<``)."""
    assert underperforms_by(candidate=0.75, incumbent=1.0, fraction=0.25) is False


def test_underperforms_within_25_percent_survives() -> None:
    """A candidate 10% below survives the smoke stage."""
    assert underperforms_by(candidate=0.90, incumbent=1.0, fraction=0.25) is False


def test_underperforms_better_than_incumbent_survives() -> None:
    """A candidate at or above the incumbent never underperforms."""
    assert underperforms_by(candidate=1.10, incumbent=1.0, fraction=0.25) is False


# --- non-inferiority (the experiment verdict) --------------------------------


def test_a_clearly_non_inferior_candidate_passes_at_the_stated_margin() -> None:
    """A cheaper model holding the outcome rate within the margin is non-inferior.

    This is the ONLY question worth asking of a cost-saving switch. Superiority
    ("is it better?") is the wrong test — nobody claims the cheap model wins; the
    claim is that it does not lose by more than an amount the business accepts.
    Testing for superiority would reject every good switch.
    """
    verdict = non_inferiority(
        candidate_successes=1_000,
        candidate_n=12_400,
        incumbent_successes=1_020,
        incumbent_n=12_400,
        margin=0.01,
    )

    assert verdict.decided is True
    assert verdict.non_inferior is True
    assert verdict.p_value < 0.05


def test_a_candidate_that_loses_more_than_the_margin_fails() -> None:
    """Losing 3 points against a 1-point margin is a real regression, not noise."""
    verdict = non_inferiority(
        candidate_successes=640,
        candidate_n=12_400,
        incumbent_successes=1_020,
        incumbent_n=12_400,
        margin=0.01,
    )

    assert verdict.decided is True
    assert verdict.non_inferior is False


def test_too_little_data_is_undecided_never_a_verdict() -> None:
    """The failure this whole test exists to prevent: a confident answer from noise.

    At 200 units per arm nothing can be concluded about a 1-point margin on an 8%
    baseline. Returning `non_inferior=False` would read as "the candidate is worse"
    and returning True would be a fabrication; both are lies about what the data
    supports. Undecided is the honest third state.
    """
    verdict = non_inferiority(
        candidate_successes=16,
        candidate_n=200,
        incumbent_successes=17,
        incumbent_n=200,
        margin=0.01,
    )

    assert verdict.decided is False
    assert verdict.non_inferior is None


def test_an_empty_arm_is_undecided_rather_than_a_divide_by_zero() -> None:
    verdict = non_inferiority(
        candidate_successes=0,
        candidate_n=0,
        incumbent_successes=10,
        incumbent_n=100,
        margin=0.01,
    )

    assert verdict.decided is False
    assert verdict.non_inferior is None


def test_required_sample_size_matches_the_documented_scale() -> None:
    """~9.3k per arm for a 1pp margin on an 8.2% baseline, at 80% power.

    Hand-checked: (z_.95 + z_.80)^2 * 2p(1-p) / margin^2 = 9307.96 -> 9308. The
    plan's "~12k" figure assumed higher power; the standard 80% sizing is this.
    Either way the point stands unchanged — a customer doing 500 units a month
    cannot power this in a year, and saying so up front beats five weeks ending
    in "undecided".
    """
    n = required_sample_size(baseline_rate=0.082, margin=0.01)

    assert n == 9_308

    # A wider margin is cheaper to prove; a narrower one is far more expensive.
    assert required_sample_size(baseline_rate=0.082, margin=0.02) < n
    assert required_sample_size(baseline_rate=0.082, margin=0.005) > n
