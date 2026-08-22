"""The CostEvent — one HTTP attempt's cost, provenance-tagged (§5.2).

Money is :class:`~decimal.Decimal` (never float), and ``cost_usd`` is ``None``
when billing is genuinely uncertain (PTU/provisioned-throughput, client-abort) —
we refuse to publish a fabricated number (H10/§13). The dedup key is
``(run_id, attempt_id)`` so at-least-once ingest never double-counts (M7).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator
from valuemaxx.core.base import TenantScopedModel
from valuemaxx.core.enums import CaptureGranularity
from valuemaxx.core.ids import AttemptId, CostEventId, RunId
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.tokens import TokenVector


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
    # None when the producer did not measure it. A fabricated 0 would read as
    # instantaneous, and only the proxy that made the call ever sees this clock —
    # there is no later stage that could backfill it.
    latency_ms: int | None = None
    # Gateway-computed request configuration. Optional for legacy/SDK spans, but an
    # observed stamp is complete so attribution never mixes partial identities.
    call_site_id: str | None = None
    system_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tools_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    params_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    config_identity: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    config_identity_weak: bool = False
    http_status: int | None = Field(default=None, ge=100, le=599)

    @model_validator(mode="after")
    def _config_stamp_is_complete(self) -> CostEvent:
        hashes = (self.system_hash, self.tools_hash, self.params_hash, self.config_identity)
        if any(value is not None for value in hashes) and any(value is None for value in hashes):
            raise ValueError("gateway config stamp hashes must be supplied together")
        if self.config_identity_weak and self.config_identity is None:
            raise ValueError("a weak identity label requires a config stamp")
        return self

    @property
    def idempotency_key(self) -> tuple[RunId, AttemptId]:
        """The dedup key for at-least-once ingest (M7): (run_id, attempt_id)."""
        return (self.run_id, self.attempt_id)


__all__ = ["CostEvent"]
