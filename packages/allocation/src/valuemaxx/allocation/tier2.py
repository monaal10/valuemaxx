"""Tier-2 shared-proportional allocation — split by the declared key (§5.4).

A Tier-2 shared cost (e.g. a vector DB) is split across consumers *proportionally*
by the declared ``allocation_key`` (requests, tokens, seats, ...). Every resulting
:class:`~valuemaxx.core.AllocatedLine` is ``SHARED_PROPORTIONAL`` / ``allocated`` —
never ``measured`` — at MEDIUM confidence, carrying the allocation key, rule version,
and sensitivity so the inference is fully labeled (an allocated number must never read
as a measured one, §3.1).

The split uses the same exact :func:`~valuemaxx.allocation._allocator.allocate`
largest-remainder allocator (Decimal, ``ROUND_HALF_EVEN``) so the parts sum exactly
to the shared total.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.allocation._allocator import allocate
from valuemaxx.core import AllocatedLine, AllocationTier, ConfidenceLabel, Provenance

if TYPE_CHECKING:
    from collections.abc import Mapping
    from decimal import Decimal

    from valuemaxx.allocation.config import SharedCostInput


def allocate_proportional(
    total: Decimal, weights: Mapping[str, Decimal]
) -> dict[str, Decimal]:
    """Split ``total`` across consumer ``weights`` so the parts sum exactly.

    A thin, named re-export of the shared largest-remainder allocator for the Tier-2
    proportional split (so callers don't reach into the private module).
    """
    return allocate(total, weights)


def tier2_lines(
    shared: SharedCostInput, weights: Mapping[str, Decimal]
) -> tuple[AllocatedLine, ...]:
    """Split one Tier-2 shared cost across consumers into allocated lines.

    Args:
        shared: the declared shared cost (must be ``shared_proportional`` with a key).
        weights: per-consumer weights by the declared allocation key.

    Returns:
        One ``SHARED_PROPORTIONAL`` / ``allocated`` line per consumer, summing exactly
        to ``shared.amount_usd``. Empty when there are no consumers.

    Raises:
        ValueError: if ``shared`` has no ``allocation_key`` (cannot split by key).
    """
    if shared.allocation_key is None:
        raise ValueError(
            f"shared cost {shared.name!r} has no allocation_key to split proportionally"
        )
    if not weights:
        return ()
    parts = allocate(shared.amount_usd, weights)
    return tuple(
        AllocatedLine(
            tier=AllocationTier.SHARED_PROPORTIONAL,
            label=Provenance.ALLOCATED,
            amount_usd=amount,
            allocation_key=shared.allocation_key,
            confidence=ConfidenceLabel.MEDIUM,
            sensitivity_pct=shared.sensitivity_pct,
            rule_version=shared.rule_version,
            quarantined=False,
        )
        for amount in parts.values()
    )


__all__ = ["allocate_proportional", "tier2_lines"]
