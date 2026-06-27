"""Mixed-state reconciliation query semantics (§5.3a, M3).

A time-range cost query can span days in *different* reconciliation states:
``provider_reconciled`` (the invoice landed), ``provisional`` (estimate with a
true-up still expected), and ``estimate_only`` (no reconciliation path). Collapsing
these into one number would let an estimate masquerade as billed, so the query
projects an honest :class:`~valuemaxx.core.ProvenanceBreakdown` partitioned by state
and carries any open :class:`~valuemaxx.core.DriftAlert`\\ s alongside — a true-up
never silently swaps a number (M3).

``CostSlice`` and ``ReconciliationView`` are plain frozen dataclasses; the
authoritative domain artifact is the core :class:`~valuemaxx.core.ProvenanceBreakdown`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.core import DriftAlert, ProvenanceBreakdown, ReconciliationState

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class CostSlice:
    """One reconciliation-state-tagged amount within a query window (NOT a domain model)."""

    state: ReconciliationState
    amount_usd: Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationView:
    """The mixed-state projection of a cost query (NOT a domain model).

    Attributes:
        breakdown: the core :class:`~valuemaxx.core.ProvenanceBreakdown` (reconciled /
            provisional / estimate_only, summing to the window total).
        drift_alerts: the open >10% drift alerts intersecting the window (M3).
    """

    breakdown: ProvenanceBreakdown
    drift_alerts: tuple[DriftAlert, ...] = field(default=())


def build_breakdown(
    slices: Iterable[CostSlice],
    *,
    drift_alerts: Iterable[DriftAlert] = (),
) -> ReconciliationView:
    """Partition cost slices by reconciliation state into an honest breakdown.

    Args:
        slices: the reconciliation-state-tagged amounts in the window.
        drift_alerts: any open drift alerts to carry alongside (never dropped).

    Returns:
        A :class:`ReconciliationView` whose breakdown sums to the window total and
        whose ``drift_alerts`` carry the surfaced gaps.

    Raises:
        ValueError: if any slice amount is negative.
    """
    reconciled = Decimal(0)
    provisional = Decimal(0)
    estimate_only = Decimal(0)
    for slice_ in slices:
        if slice_.amount_usd < 0:
            raise ValueError("cost slice amounts must be non-negative")
        if slice_.state is ReconciliationState.PROVIDER_RECONCILED:
            reconciled += slice_.amount_usd
        elif slice_.state is ReconciliationState.PROVISIONAL:
            provisional += slice_.amount_usd
        else:  # ReconciliationState.ESTIMATE_ONLY
            estimate_only += slice_.amount_usd

    breakdown = ProvenanceBreakdown(
        reconciled_usd=reconciled,
        provisional_usd=provisional,
        estimate_only_usd=estimate_only,
    )
    return ReconciliationView(breakdown=breakdown, drift_alerts=tuple(drift_alerts))


__all__ = ["CostSlice", "ReconciliationView", "build_breakdown"]
