"""Mixed-state reconciliation query — the ProvenanceBreakdown projection (§5.3a, M3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from valuemaxx.core import DriftAlert, ProvenanceBreakdown, ReconciliationState
from valuemaxx.reconciliation.query import CostSlice, ReconciliationView, build_breakdown


def _slice(state: ReconciliationState, usd: str) -> CostSlice:
    return CostSlice(state=state, amount_usd=Decimal(usd))


def test_breakdown_partitions_by_reconciliation_state() -> None:
    """Slices are partitioned reconciled / provisional / estimate_only."""
    view = build_breakdown(
        [
            _slice(ReconciliationState.PROVIDER_RECONCILED, "100"),
            _slice(ReconciliationState.PROVISIONAL, "30"),
            _slice(ReconciliationState.ESTIMATE_ONLY, "20"),
        ]
    )
    assert isinstance(view, ReconciliationView)
    assert isinstance(view.breakdown, ProvenanceBreakdown)
    assert view.breakdown.reconciled_usd == Decimal("100")
    assert view.breakdown.provisional_usd == Decimal("30")
    assert view.breakdown.estimate_only_usd == Decimal("20")


def test_breakdown_sums_to_total() -> None:
    """The breakdown's parts sum to the total (no number silently dropped)."""
    view = build_breakdown(
        [
            _slice(ReconciliationState.PROVIDER_RECONCILED, "100"),
            _slice(ReconciliationState.PROVIDER_RECONCILED, "50"),
            _slice(ReconciliationState.PROVISIONAL, "25"),
        ]
    )
    assert view.breakdown.total_usd == Decimal("175")
    assert view.breakdown.reconciled_usd == Decimal("150")


def test_breakdown_carries_drift_alerts() -> None:
    """Drift alerts ride the view — a true-up never silently swaps a number (M3)."""
    alert = DriftAlert(
        match_key=("anthropic", "p", "m", "output", "2026-06-27"),
        drift_pct=Decimal("30"),
        ranked_causes=("cache_mispricing",),
    )
    view = build_breakdown(
        [_slice(ReconciliationState.PROVIDER_RECONCILED, "100")],
        drift_alerts=[alert],
    )
    assert view.drift_alerts == (alert,)


def test_empty_view_is_all_zero() -> None:
    """An empty window is an honest all-zero breakdown, not an error."""
    view = build_breakdown([])
    assert view.breakdown.total_usd == Decimal("0")
    assert view.breakdown.pct_reconciled == Decimal("0")
    assert view.drift_alerts == ()


def test_pct_reconciled_reflects_share() -> None:
    """pct_reconciled is the reconciled share of the total."""
    view = build_breakdown(
        [
            _slice(ReconciliationState.PROVIDER_RECONCILED, "75"),
            _slice(ReconciliationState.ESTIMATE_ONLY, "25"),
        ]
    )
    assert view.breakdown.pct_reconciled == Decimal("75")


def test_manual_reconciled_counts_as_reconciled() -> None:
    """A manually-reconciled (CSV) slice counts toward the reconciled share."""
    view = build_breakdown(
        [_slice(ReconciliationState.PROVIDER_RECONCILED, "40")],
    )
    assert view.breakdown.reconciled_usd == Decimal("40")


def test_negative_amount_rejected() -> None:
    """A negative slice amount is rejected (cost slices are non-negative)."""
    with pytest.raises(ValueError, match="non-negative"):
        build_breakdown([_slice(ReconciliationState.PROVISIONAL, "-1")])
