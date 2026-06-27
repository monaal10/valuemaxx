"""Proration — distribute an authoritative billed total across estimates (§5.3).

The reconciliation contract is exactness: after a daily invoice arrives, every
per-request estimate is scaled by ``proration_factor = billed_total /
sum(estimates)`` so the reconciled values sum to the billed total *to the last
unit*. Naive scaling-then-rounding leaks a rounding residue, so we apply a
largest-remainder pass: quantize each share down/nearest, then hand the leftover
ulps to the shares with the largest fractional remainders. The result is
deterministic and order-stable.

All arithmetic is :class:`~decimal.Decimal` with ``ROUND_HALF_EVEN`` (banker's
rounding). Floats are rejected at the boundary — money is never float (M7,
AGENTS.md §0). Shares are quantized to 10 decimal places, matching the storage
column ``NUMERIC(20, 10)``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

# 10 decimal places == the storage precision (NUMERIC(20,10)).
_QUANTUM = Decimal("0.0000000001")
_ULP = _QUANTUM


def _require_decimals(estimates: tuple[object, ...]) -> None:
    """Reject any non-Decimal estimate at the boundary (money is never float).

    Typed ``tuple[object, ...]`` deliberately: this is the runtime boundary guard
    that catches a float/str slipping through an untyped caller (the wire/config
    edge), turning silent mispricing into an explicit ``TypeError``.
    """
    for estimate in estimates:
        if not isinstance(estimate, Decimal):
            raise TypeError(
                f"estimates must be Decimal, not {type(estimate).__name__}; "
                "money math never uses float (AGENTS.md §0)"
            )


def proration_factor(estimates: tuple[Decimal, ...], billed_total: Decimal) -> Decimal:
    """Return ``billed_total / sum(estimates)`` (the scale applied to each estimate).

    Raises:
        ValueError: if the estimates sum to zero while the billed total is not
            (you cannot distribute a non-zero invoice across nothing).
    """
    total = sum(estimates, Decimal(0))
    if total == 0:
        if billed_total == 0:
            return Decimal(0)
        raise ValueError("cannot prorate a non-zero billed total across estimates that sum to zero")
    return billed_total / total


def prorate(estimates: tuple[Decimal, ...], billed_total: Decimal) -> tuple[Decimal, ...]:
    """Scale ``estimates`` so the reconciled shares sum exactly to ``billed_total``.

    Uses the largest-remainder method: each share is the estimate's proportional
    slice quantized down to 10dp via ``ROUND_HALF_EVEN``; the residue
    (``billed_total - sum(quantized)``) is distributed one ulp at a time to the
    shares with the largest dropped remainders (ties broken by original index, so
    the result is deterministic). The returned tuple sums to ``billed_total``
    exactly and is positionally aligned with ``estimates``.

    Args:
        estimates: the per-request provisional cost estimates (at least one).
        billed_total: the authoritative daily total to distribute.

    Returns:
        One reconciled share per estimate, summing exactly to ``billed_total``.

    Raises:
        ValueError: if ``estimates`` is empty, or sums to zero with a non-zero
            ``billed_total``.
        TypeError: if any estimate is not a :class:`~decimal.Decimal`.
    """
    if not estimates:
        raise ValueError("prorate requires at least one estimate")
    _require_decimals(estimates)

    total = sum(estimates, Decimal(0))
    if total == 0:
        if billed_total == 0:
            return tuple(Decimal(0).quantize(_QUANTUM) for _ in estimates)
        raise ValueError("cannot prorate a non-zero billed total across estimates that sum to zero")

    factor = billed_total / total
    # Exact ideal share per estimate, then quantize each down to the quantum.
    exact_shares = [estimate * factor for estimate in estimates]
    floored = [share.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN) for share in exact_shares]

    residue = billed_total - sum(floored, Decimal(0))
    # The residue is a whole number of ulps (both sides are quantized to the quantum).
    steps = int((residue / _ULP).to_integral_value(rounding=ROUND_HALF_EVEN))
    if steps == 0:
        return tuple(floored)

    direction = _ULP if steps > 0 else -_ULP
    # Rank shares by the remainder dropped during quantization: the shares that lost
    # the most (gained the most, when steps < 0) absorb the leftover ulps first.
    remainders = [exact - q for exact, q in zip(exact_shares, floored, strict=True)]
    order = sorted(
        range(len(estimates)),
        key=lambda i: (remainders[i], -i),
        reverse=steps > 0,
    )
    result = list(floored)
    for k in range(abs(steps)):
        idx = order[k % len(order)]
        result[idx] = result[idx] + direction
    return tuple(result)


__all__ = ["prorate", "proration_factor"]
