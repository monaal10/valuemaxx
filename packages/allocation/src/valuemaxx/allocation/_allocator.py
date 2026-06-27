"""The shared largest-remainder allocator — exact Decimal split (§5.4).

A single, internal money-splitting primitive used by Tier-2 proportional allocation
(and the same algorithm reconciliation uses for proration): given a total and a set
of weights, distribute the total so the parts sum to it *exactly*. Each part is the
weighted slice quantized to 10dp via ``ROUND_HALF_EVEN`` (banker's rounding); the
residue is handed one ulp at a time to the largest dropped remainders (ties broken
by a stable key order), so the split is deterministic and order-stable.

Money is :class:`~decimal.Decimal` throughout — never float (AGENTS.md §0). This lives
inside ``valuemaxx.allocation`` (logic packages never import a sibling) and mirrors the
reconciliation proration math by design.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Mapping

# 10 decimal places == the storage precision (NUMERIC(20, 10)).
_QUANTUM = Decimal("0.0000000001")

_K = TypeVar("_K")


def _require_decimal(value: object, *, label: str) -> None:
    """Runtime boundary guard: reject a non-Decimal amount (money is never float)."""
    if not isinstance(value, Decimal):
        raise TypeError(
            f"{label} must be Decimal, not {type(value).__name__}; "
            "allocation money is never float (AGENTS.md §0)"
        )


def allocate(total: Decimal, weights: Mapping[_K, Decimal]) -> dict[_K, Decimal]:
    """Split ``total`` across ``weights`` so the parts sum exactly to ``total``.

    Args:
        total: the amount to distribute (exact Decimal).
        weights: per-key weights; their relative sizes set each key's share.

    Returns:
        One Decimal share per key, summing exactly to ``total`` (10dp quantized).

    Raises:
        ValueError: if the weights sum to zero while ``total`` is non-zero.
        TypeError: if ``total`` or any weight is not a :class:`~decimal.Decimal`.
    """
    _require_decimal(total, label="total")
    keys = list(weights.keys())
    if not keys:
        return {}
    for weight in weights.values():
        _require_decimal(weight, label="weight")

    weight_total = sum(weights.values(), Decimal(0))
    if weight_total == 0:
        if total == 0:
            return {key: Decimal(0).quantize(_QUANTUM) for key in keys}
        raise ValueError("cannot allocate a non-zero total across zero total weight")

    exact = {key: total * weights[key] / weight_total for key in keys}
    floored = {
        key: value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN) for key, value in exact.items()
    }

    residue = total - sum(floored.values(), Decimal(0))
    steps = int((residue / _QUANTUM).to_integral_value(rounding=ROUND_HALF_EVEN))
    if steps == 0:
        return floored

    direction = _QUANTUM if steps > 0 else -_QUANTUM
    remainders = {key: exact[key] - floored[key] for key in keys}
    order = sorted(
        keys,
        key=lambda k: (remainders[k], keys.index(k)),
        reverse=steps > 0,
    )
    result = dict(floored)
    for i in range(abs(steps)):
        key = order[i % len(order)]
        result[key] = result[key] + direction
    return result


__all__ = ["allocate"]
