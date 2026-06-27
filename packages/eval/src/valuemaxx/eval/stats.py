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

from dataclasses import dataclass

# z-score for a two-sided 95% interval (standard normal quantile at 0.975).
_Z_95: float = 1.959963984540054

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
