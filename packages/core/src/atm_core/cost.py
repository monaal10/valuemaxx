"""The CostEvent — one HTTP attempt's cost, provenance-tagged (§5.2).

Money is :class:`~decimal.Decimal` (never float), and ``cost_usd`` is ``None``
when billing is genuinely uncertain (PTU/provisioned-throughput, client-abort) —
we refuse to publish a fabricated number (H10/§13). The dedup key is
``(run_id, attempt_id)`` so at-least-once ingest never double-counts (M7).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from atm_core.base import TenantScopedModel
from atm_core.enums import CaptureGranularity
from atm_core.ids import AttemptId, CostEventId, RunId
from atm_core.provenance import ProvenanceLabel
from atm_core.tokens import TokenVector


class CostEvent(TenantScopedModel):
    """One HTTP attempt's token usage and cost, carrying its provenance label."""

    id: CostEventId
    run_id: RunId
    attempt_id: AttemptId
    provider: str
    model: str
    tokens: TokenVector
    capture_granularity: CaptureGranularity
    provenance: ProvenanceLabel
    cost_usd: Decimal | None
    is_streaming: bool
    partial_recovered: bool
    billing_uncertain_abort: bool
    provenance_warnings: tuple[str, ...]
    occurred_at: datetime

    @property
    def idempotency_key(self) -> tuple[RunId, AttemptId]:
        """The dedup key for at-least-once ingest (M7): (run_id, attempt_id)."""
        return (self.run_id, self.attempt_id)


__all__ = ["CostEvent"]
