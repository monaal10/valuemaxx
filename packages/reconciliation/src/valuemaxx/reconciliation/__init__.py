"""valuemaxx.reconciliation — provider cost true-up (§5.3).

Reconciliation closes the gap between provisional cost *estimates* and the
*authoritative* billed total a provider reports:

  * :func:`~valuemaxx.reconciliation.proration.prorate` distributes a billed total
    across per-request estimates so the reconciled values sum to it *exactly*
    (largest-remainder, ``ROUND_HALF_EVEN``, never float);
  * :func:`~valuemaxx.reconciliation.matcher.match_key_of` groups by
    (provider, project, model, token_class, day);
  * :func:`~valuemaxx.reconciliation.drift.classify_drift` flags >10% drift with
    ranked causes;
  * :func:`~valuemaxx.reconciliation.manual_csv.parse_manual_csv` ingests the
    Bedrock/Vertex/Azure CSV-upload path (``manual_reconciled``);
  * the :mod:`~valuemaxx.reconciliation.provider_api` clients fetch the OpenAI /
    Anthropic authoritative totals (admin-key gated, key never logged);
  * :func:`~valuemaxx.reconciliation.service.reconcile_day` appends an additive
    :class:`~valuemaxx.core.ReconciliationRecord` — never an UPDATE to the estimate;
  * :func:`~valuemaxx.reconciliation.query.build_breakdown` projects a mixed
    reconciliation-state window into an honest
    :class:`~valuemaxx.core.ProvenanceBreakdown`.

The package depends only on ``valuemaxx.core`` ABCs/Protocols and
``valuemaxx.capabilities``; it never imports ``valuemaxx.store`` or a sibling logic
package. :func:`register` projects its two capabilities onto the registry.
"""

from __future__ import annotations

from valuemaxx.reconciliation.capabilities import register
from valuemaxx.reconciliation.drift import classify_drift, drift_pct
from valuemaxx.reconciliation.manual_csv import ManualCsvError, parse_manual_csv
from valuemaxx.reconciliation.matcher import (
    group_by_match_key,
    match_key_of,
    parse_match_key,
)
from valuemaxx.reconciliation.proration import prorate, proration_factor
from valuemaxx.reconciliation.provider_api import (
    AdminKeyRequiredError,
    AnthropicCostClient,
    BilledTotal,
    OpenAICostClient,
    ProviderCostApiError,
)
from valuemaxx.reconciliation.query import CostSlice, ReconciliationView, build_breakdown
from valuemaxx.reconciliation.service import (
    EstimateRow,
    ReconciliationOutcome,
    reconcile_day,
    reconcile_match_key,
)

__all__ = [
    "AdminKeyRequiredError",
    "AnthropicCostClient",
    "BilledTotal",
    "CostSlice",
    "EstimateRow",
    "ManualCsvError",
    "OpenAICostClient",
    "ProviderCostApiError",
    "ReconciliationOutcome",
    "ReconciliationView",
    "build_breakdown",
    "classify_drift",
    "drift_pct",
    "group_by_match_key",
    "match_key_of",
    "parse_manual_csv",
    "parse_match_key",
    "prorate",
    "proration_factor",
    "reconcile_day",
    "reconcile_match_key",
    "register",
]
