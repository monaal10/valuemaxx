"""Pure statistics for the eval funnel — closed-form, deterministic, no native deps.

Every statistic the recommendation needs is a small closed-form computation, so
these are implemented in pure ``math`` (no scipy/numpy): the funnel stays fully
deterministic and testable, and there is no heavyweight native build to install.

- :func:`wilson_ci` — the Wilson score interval (the significance layer §8.6 adds
  on top of raw parity), at 95% via the standard ``z = 1.959963985``.
- :func:`percentiles` — p50/p95/p99 latency quantiles via linear interpolation.
- :func:`ci_separated` — whether two confidence intervals are strictly disjoint
  (the confirmation-stage gate; touching is NOT separated).
- :func:`relative_improvement` / :func:`meets_hysteresis` — switching hysteresis
  (>= 0.15) so the recommendation never churns on noise (§8.7).
- :func:`underperforms_by` — the smoke-stage elimination test (strict ``<``, no CI
  requirement, §8.4 M4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# z-score for a two-sided 95% interval (standard normal quantile at 0.975).
_Z_95: float = 1.959963984540054

# A zero/negative margin asks to prove exact equality, which no finite sample can do.
_IMPOSSIBLE_SAMPLE: int = 2**31

Interval = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Percentiles:
    """The three named latency quantiles (ms), always p50 <= p95 <= p99.

    A plain frozen dataclass (NOT a pydantic domain model): it is an eval-local
    computation result, so it does not live in ``valuemaxx.core`` and does not
    trip the ``no_type_outside_core`` rule.
    """

    p50: float
    p95: float
    p99: float


def wilson_ci(*, successes: int, n: int) -> Interval:
    """Return the 95% Wilson score interval ``(low, high)`` for ``successes``/``n``.

    The Wilson interval is well-behaved at the extremes (unlike the normal
    approximation, it stays inside ``[0, 1]`` and is non-degenerate at 0 and n
    successes), which is exactly why §8.6 uses it for parity significance.

    Args:
        successes: the number of successes observed (0 <= successes <= n).
        n: the number of trials (must be positive).

    Returns:
        The ``(low, high)`` bounds, both within ``[0, 1]`` and ``low <= high``.

    Raises:
        ValueError: if ``n`` is not positive or ``successes`` is out of range.
    """
    if n <= 0:
        raise ValueError("n must be positive to form a confidence interval")
    if successes < 0 or successes > n:
        raise ValueError(f"successes ({successes}) must be in [0, n] for n={n}")
    z = _Z_95
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = (z / denom) * ((p * (1.0 - p) / n + z2 / (4.0 * n * n)) ** 0.5)
    low = center - margin
    high = center + margin
    return (max(0.0, low), min(1.0, high))


def percentiles(samples: list[float]) -> Percentiles:
    """Return the p50/p95/p99 of ``samples`` via linear interpolation.

    The input need not be sorted (it is sorted internally), so the result is
    order-independent. A single sample collapses all three percentiles to it.

    Args:
        samples: the latency samples (must be non-empty).

    Raises:
        ValueError: if ``samples`` is empty.
    """
    if not samples:
        raise ValueError("percentiles require at least one sample")
    ordered = sorted(samples)
    return Percentiles(
        p50=_quantile(ordered, 0.50),
        p95=_quantile(ordered, 0.95),
        p99=_quantile(ordered, 0.99),
    )


def _quantile(ordered: list[float], q: float) -> float:
    """Linear-interpolated quantile of a pre-sorted, non-empty sequence."""
    if len(ordered) == 1:
        return ordered[0]
    rank = q * (len(ordered) - 1)
    low_idx = int(rank)
    if low_idx >= len(ordered) - 1:
        return ordered[-1]
    frac = rank - low_idx
    return ordered[low_idx] + frac * (ordered[low_idx + 1] - ordered[low_idx])


def ci_separated(a: Interval, b: Interval) -> bool:
    """Whether intervals ``a`` and ``b`` are strictly disjoint (no overlap, no touch).

    Strict by design: two intervals that merely touch at an endpoint are NOT
    separated, so a recommendation requires a clear gap (§8.4 confirmation stage).
    """
    a_low, a_high = a
    b_low, b_high = b
    return a_high < b_low or b_high < a_low


def relative_improvement(*, new: float, old: float) -> float:
    """Return ``(new - old) / |old|``; ``relative_improvement(0, 0) == 0``.

    A zero baseline with no change is defined as 0.0 (never NaN/inf) so the
    hysteresis check is total.
    """
    if old == 0.0:
        return 0.0 if new == 0.0 else float("inf") if new > 0.0 else float("-inf")
    return (new - old) / abs(old)


def meets_hysteresis(*, new: float, old: float, threshold: float = 0.15) -> bool:
    """Whether ``|new - old| / |old| >= threshold`` (default 0.15, §8.7).

    Switching is only surfaced when the relative change meets the hysteresis band,
    which prevents churning the recommendation on noise. A zero baseline with a
    non-zero new value always meets it.
    """
    if old == 0.0:
        return new != 0.0
    # A small tolerance so a value that is exactly the threshold in exact
    # arithmetic (e.g. 0.15) is not rejected by binary-float representation
    # (0.15000000000000013 vs 0.1499999999999999).
    return abs(new - old) / abs(old) >= threshold - 1e-9


def underperforms_by(*, candidate: float, incumbent: float, fraction: float) -> bool:
    """Whether ``candidate`` is more than ``fraction`` below ``incumbent`` (strict ``<``).

    The smoke-stage elimination test (§8.4 M4): a candidate scoring strictly below
    ``incumbent * (1 - fraction)`` is dropped — with NO CI requirement at this
    stage. At exactly the boundary the candidate survives (strict inequality).
    """
    return candidate < incumbent * (1.0 - fraction)


__all__ = [
    "Interval",
    "Percentiles",
    "ci_separated",
    "meets_hysteresis",
    "percentiles",
    "relative_improvement",
    "underperforms_by",
    "wilson_ci",
]


@dataclass(frozen=True, slots=True)
class NonInferiorityVerdict:
    """The result of one non-inferiority test, with UNDECIDED as a real state.

    ``decided`` is false when the data cannot support any conclusion at this margin.
    That is not a failure of the candidate and must never render as one: a caller
    that collapses undecided into "worse" turns thin data into a rejection, and one
    that collapses it into "fine" ships a regression. ``non_inferior`` is None
    exactly when ``decided`` is false, so the two cannot drift apart.
    """

    decided: bool
    non_inferior: bool | None
    p_value: float
    candidate_rate: float
    incumbent_rate: float
    margin: float
    n_per_arm: int


def non_inferiority(
    *,
    candidate_successes: int,
    candidate_n: int,
    incumbent_successes: int,
    incumbent_n: int,
    margin: float,
    alpha: float = 0.05,
) -> NonInferiorityVerdict:
    """Test whether the candidate's outcome rate is within ``margin`` of the incumbent.

    The question a cost-saving switch actually poses is NOT "is the cheap model
    better" — nobody claims that, and a superiority test would reject every good
    switch. It is "does it lose by less than an amount the business has declared
    acceptable". So the null hypothesis is that the candidate is worse by at least
    ``margin``, and rejecting it earns the non-inferior verdict.

    One-sided z-test on the difference of proportions, using the standard-error
    form with the margin shifted into the numerator. Pure closed-form, matching
    this module's no-scipy rule; the normal approximation is sound at the sample
    sizes a non-inferiority test needs (thousands per arm) and the undecided guard
    below covers the regime where it would not be.
    """
    if candidate_n <= 0 or incumbent_n <= 0:
        return NonInferiorityVerdict(
            decided=False,
            non_inferior=None,
            p_value=1.0,
            candidate_rate=0.0,
            incumbent_rate=0.0,
            margin=margin,
            n_per_arm=0,
        )

    p_c = candidate_successes / candidate_n
    p_i = incumbent_successes / incumbent_n
    n_per_arm = min(candidate_n, incumbent_n)

    se = math.sqrt(p_c * (1.0 - p_c) / candidate_n + p_i * (1.0 - p_i) / incumbent_n)
    if se == 0.0:
        # Both arms degenerate (all-success or all-failure). No variance means no
        # test; claiming a verdict off a zero standard error is how a 100%-of-8
        # sample becomes "proven non-inferior".
        return NonInferiorityVerdict(
            decided=False,
            non_inferior=None,
            p_value=1.0,
            candidate_rate=p_c,
            incumbent_rate=p_i,
            margin=margin,
            n_per_arm=n_per_arm,
        )

    z = (p_c - p_i + margin) / se
    p_value = 1.0 - _normal_cdf(z)

    # The power guard. Without it a small sample that happens to look good returns
    # a significant p-value off noise — the single most dangerous output this
    # module could produce, because it reads exactly like a real result.
    if n_per_arm < required_sample_size(baseline_rate=p_i, margin=margin, alpha=alpha):
        return NonInferiorityVerdict(
            decided=False,
            non_inferior=None,
            p_value=p_value,
            candidate_rate=p_c,
            incumbent_rate=p_i,
            margin=margin,
            n_per_arm=n_per_arm,
        )

    return NonInferiorityVerdict(
        decided=True,
        non_inferior=p_value < alpha,
        p_value=p_value,
        candidate_rate=p_c,
        incumbent_rate=p_i,
        margin=margin,
        n_per_arm=n_per_arm,
    )


def required_sample_size(
    *, baseline_rate: float, margin: float, alpha: float = 0.05, power: float = 0.80
) -> int:
    """Units PER ARM needed to decide non-inferiority at ``margin``.

    The gate that decides whether an experiment is worth starting. A customer whose
    monthly volume is below this cannot power the test in any reasonable window, and
    telling them so up front is far better than five weeks ending in "undecided".

    Standard one-sided two-proportion sizing: n = (z_alpha + z_beta)^2 * 2p(1-p) / margin^2.
    """
    if margin <= 0.0:
        return _IMPOSSIBLE_SAMPLE
    p = min(max(baseline_rate, 1e-6), 1.0 - 1e-6)
    z_a = _z_quantile(1.0 - alpha)
    z_b = _z_quantile(power)
    return math.ceil(((z_a + z_b) ** 2) * 2.0 * p * (1.0 - p) / (margin**2))


def _normal_cdf(z: float) -> float:
    """Standard normal CDF via the error function (exact to double precision)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _z_quantile(p: float) -> float:
    """Inverse standard normal CDF — Acklam's rational approximation.

    Accurate to ~1e-9 over the range, which is far tighter than sample-size
    arithmetic needs, and keeps the no-native-dependency rule intact.
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p must be in (0, 1)")
    a = (
        -39.69683028665376,
        220.9460984245205,
        -275.9285104469687,
        138.3577518672690,
        -30.66479806614716,
        2.506628277459239,
    )
    b = (
        -54.47609879822406,
        161.5858368580409,
        -155.6989798598866,
        66.80131188771972,
        -13.28068155288572,
    )
    c = (
        -0.007784894002430293,
        -0.3223964580411365,
        -2.400758277161838,
        -2.549732539343734,
        4.374664141464968,
        2.938163982698783,
    )
    d = (0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416)
    p_low, p_high = 0.02425, 1.0 - 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > p_high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )
