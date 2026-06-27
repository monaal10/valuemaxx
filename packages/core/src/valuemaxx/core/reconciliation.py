"""ReconciliationRecord — the additive estimate->invoice true-up delta (§5.3).

Reconciliation is *never* an UPDATE to the estimate: the estimate is immutable
and the true-up is captured as an additive record carrying the proration factor
and drift. No field on this model points back to mutate an estimate (asserted by
an AST test in core and the ``additive_reconciliation`` conformance rule).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import model_validator
from valuemaxx.core.base import StrictModel, TenantScopedModel
from valuemaxx.core.ids import ReconciliationRecordId


class ReconciliationRecord(TenantScopedModel):
    """An additive true-up of estimated cost against the authoritative daily total."""

    id: ReconciliationRecordId
    # (provider, project/workspace, model, token_class, day)
    match_key: tuple[str, str, str, str, str]
    estimated_total: Decimal
    billed_total: Decimal
    proration_factor: Decimal
    drift_pct: Decimal
    drift_cause_ranked: tuple[str, ...]
    created_at: datetime


class ProvenanceBreakdown(StrictModel):
    """How much of an aggregate is reconciled vs provisional vs estimate-only (§5.3a).

    A time-range query can span days in different reconciliation states; the
    breakdown preserves that honestly rather than collapsing to one number.
    """

    reconciled_usd: Decimal
    provisional_usd: Decimal
    estimate_only_usd: Decimal

    @property
    def total_usd(self) -> Decimal:
        """The sum across all reconciliation states."""
        return self.reconciled_usd + self.provisional_usd + self.estimate_only_usd

    @property
    def pct_reconciled(self) -> Decimal:
        """The reconciled share as a percentage (0 when the total is 0)."""
        total = self.total_usd
        if total == 0:
            return Decimal(0)
        return (self.reconciled_usd / total) * Decimal(100)


class DriftAlert(StrictModel):
    """A >10% reconciliation drift alert with ranked causes (§5.3)."""

    # (provider, project/workspace, model, token_class, day)
    match_key: tuple[str, str, str, str, str]
    drift_pct: Decimal
    ranked_causes: tuple[str, ...]

    @model_validator(mode="after")
    def _causes_present(self) -> DriftAlert:
        """A drift alert must name at least one ranked cause."""
        if not self.ranked_causes:
            raise ValueError("a DriftAlert must carry at least one ranked cause")
        return self


__all__ = ["DriftAlert", "ProvenanceBreakdown", "ReconciliationRecord"]
