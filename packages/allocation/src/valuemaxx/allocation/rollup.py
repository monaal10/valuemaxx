"""Allocation rollup — assemble tiers with the pct_unallocated honesty anchor (§5.4).

:func:`build_rollup` assembles the Tier-1/2/3 lines into a per-run
:class:`~valuemaxx.core.AllocatedRollup` carrying:

  * ``pct_unallocated`` — the honesty anchor: the share of the true cost the
    measured + allocated lines do NOT account for. When shared costs are absent
    (Tier-1-only mode) this is surfaced prominently rather than smearing a guess.
  * ``confidence`` — the H7 :class:`~valuemaxx.core.RollupConfidence` with BOTH
    ``minimum_tier`` (the least-trusted member, so a single allocated line drags the
    headline down — aggregation never raises confidence) AND
    ``confidence_distribution`` (so no surface can collapse the mix to a clean number).
  * ``provenance_breakdown`` — measured dollars vs allocated dollars, never blended.

Idle-GPU overhead is held *beside* the unit cost (it is quarantined, not part of the
allocated unit total), so paying for idle silicon never inflates the apparent
cost-per-call or shrinks ``pct_unallocated``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING

from valuemaxx.core import (
    AllocatedLine,
    AllocatedRollup,
    BindingTier,
    ConfidenceLabel,
    ProvenanceBreakdown,
    RollupConfidence,
)

if TYPE_CHECKING:
    from valuemaxx.allocation.tier1 import Tier1Result
    from valuemaxx.allocation.tier3 import Tier3Result
    from valuemaxx.core import RunId, TenantId

_PCT_QUANTUM = Decimal("0.0000000001")

# Allocation confidence labels map to binding tiers for the H7 RollupConfidence:
# measured (HIGH) is exact; a proportional allocation (MEDIUM) is a candidate
# inference; fixed overhead (LOW) is the least-trusted (likely). This keeps the
# conservative-propagation invariant honest across the allocation vocabulary.
_LABEL_TO_TIER: dict[ConfidenceLabel, BindingTier] = {
    ConfidenceLabel.HIGH: BindingTier.EXACT,
    ConfidenceLabel.MEDIUM: BindingTier.CANDIDATE,
    ConfidenceLabel.LOW: BindingTier.LIKELY,
    ConfidenceLabel.ADVISORY: BindingTier.LIKELY,
}


def _confidence(lines: tuple[AllocatedLine, ...]) -> RollupConfidence:
    """Build the H7 confidence from the lines' confidence labels.

    Falls back to a single EXACT member when there are no lines, so the rollup always
    carries a valid both-fields confidence (an empty allocation is trivially exact).
    """
    if not lines:
        return RollupConfidence(
            minimum_tier=BindingTier.EXACT,
            confidence_distribution={BindingTier.EXACT: 1},
        )
    tiers = [_LABEL_TO_TIER[line.confidence] for line in lines]
    return RollupConfidence.propagate(tiers)


def build_rollup(
    tenant_id: TenantId,
    *,
    run_id: RunId,
    tier1: Tier1Result,
    tier2: tuple[AllocatedLine, ...],
    tier3: Tier3Result,
    total_true_cost_estimate: Decimal,
) -> AllocatedRollup:
    """Assemble the tiers into a per-run :class:`~valuemaxx.core.AllocatedRollup`.

    Args:
        tenant_id: the tenant scope (first, structurally required).
        run_id: the run the rollup is for.
        tier1: the Tier-1 measured result (lines + measured total).
        tier2: the Tier-2 proportional allocated lines.
        tier3: the Tier-3 fixed-overhead result (lines + idle/non-idle split).
        total_true_cost_estimate: the best estimate of the run's true fully-loaded
            cost, used to compute ``pct_unallocated``.

    Returns:
        The assembled rollup with all lines, ``pct_unallocated``, both H7 fields, and
        the measured-vs-allocated provenance breakdown.
    """
    lines = (*tier1.lines, *tier2, *tier3.lines)

    measured_total = tier1.measured_total
    allocated_total = (
        sum((line.amount_usd for line in tier2), Decimal(0))
        + tier3.fixed_overhead_in_unit_usd
    )
    # The unit cost accounts for measured + proportional + non-idle overhead. Idle GPU
    # is quarantined beside and intentionally excluded (never smeared into the unit).
    accounted = measured_total + allocated_total

    if total_true_cost_estimate <= 0:
        pct_unallocated = Decimal(0)
    else:
        unallocated = max(total_true_cost_estimate - accounted, Decimal(0))
        pct_unallocated = (
            unallocated / total_true_cost_estimate * Decimal(100)
        ).quantize(_PCT_QUANTUM, rounding=ROUND_HALF_EVEN).normalize()

    provenance_breakdown = ProvenanceBreakdown(
        reconciled_usd=measured_total,
        provisional_usd=Decimal(0),
        estimate_only_usd=allocated_total,
    )

    return AllocatedRollup(
        tenant_id=tenant_id,
        run_id=run_id,
        lines=lines,
        pct_unallocated=pct_unallocated,
        confidence=_confidence(lines),
        provenance_breakdown=provenance_breakdown,
    )


__all__ = ["build_rollup"]
