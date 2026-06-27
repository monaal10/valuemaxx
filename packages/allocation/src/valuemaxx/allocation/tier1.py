"""Tier-1 direct allocation — measured cost, one line per event (§5.4).

Tier-1 is the honest floor: directly-measured per-request cost. Each
:class:`~valuemaxx.core.CostEvent` with a known ``cost_usd`` becomes one
``DIRECT`` / ``measured`` :class:`~valuemaxx.core.AllocatedLine` at HIGH confidence.

A PTU / billing-uncertain event (``cost_usd is None``, §5.2/H10) carries no
fabricated number, so it produces **no** measured line — instead it is *counted* as
an unmeasured event so the rollup can surface it honestly in ``pct_unallocated``,
never smeared into a measured total.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.core import AllocatedLine, AllocationTier, ConfidenceLabel, Provenance

if TYPE_CHECKING:
    from collections.abc import Iterable

    from valuemaxx.core import CostEvent


@dataclass(frozen=True, slots=True)
class Tier1Result:
    """The Tier-1 (direct/measured) allocation outcome (NOT a domain model).

    Attributes:
        lines: one ``DIRECT``/``measured`` line per measured event.
        measured_total: the exact sum of the measured event costs.
        unmeasured_event_count: events excluded because their cost is unknown (PTU),
            carried so the rollup can surface them in ``pct_unallocated``.
    """

    lines: tuple[AllocatedLine, ...]
    measured_total: Decimal
    unmeasured_event_count: int


def direct_lines(events: Iterable[CostEvent]) -> Tier1Result:
    """Build the Tier-1 measured allocation lines from cost events.

    Args:
        events: the run's measured cost events.

    Returns:
        A :class:`Tier1Result` with one measured line per known-cost event, the
        measured total, and the count of unmeasured (PTU) events excluded.
    """
    lines: list[AllocatedLine] = []
    measured_total = Decimal(0)
    unmeasured = 0
    for event in events:
        if event.cost_usd is None:
            unmeasured += 1
            continue
        measured_total += event.cost_usd
        lines.append(
            AllocatedLine(
                tier=AllocationTier.DIRECT,
                label=Provenance.MEASURED,
                amount_usd=event.cost_usd,
                allocation_key=None,
                confidence=ConfidenceLabel.HIGH,
                sensitivity_pct=None,
                rule_version=None,
                quarantined=False,
            )
        )
    return Tier1Result(
        lines=tuple(lines),
        measured_total=measured_total,
        unmeasured_event_count=unmeasured,
    )


__all__ = ["Tier1Result", "direct_lines"]
