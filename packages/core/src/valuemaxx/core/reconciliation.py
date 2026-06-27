"""ReconciliationRecord — the additive estimate->invoice true-up delta (§5.3).

Reconciliation is *never* an UPDATE to the estimate: the estimate is immutable
and the true-up is captured as an additive record carrying the proration factor
and drift. No field on this model points back to mutate an estimate (asserted by
an AST test in core and the ``additive_reconciliation`` conformance rule).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from valuemaxx.core.base import TenantScopedModel
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


__all__ = ["ReconciliationRecord"]
