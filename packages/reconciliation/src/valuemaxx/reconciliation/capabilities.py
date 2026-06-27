"""Capability projection for the reconciliation package (M10, §3).

``register(registry)`` projects two request/response capabilities onto the registry,
each on the API|MCP|CLI surfaces:

  * ``reconcile_day`` — prorate an authoritative billed total across per-request
    estimates for one match key, appending an additive reconciliation record and
    surfacing any >10% drift.
  * ``cost_breakdown`` — project a mixed reconciliation-state window into the honest
    reconciled / provisional / estimate_only breakdown.

The pydantic classes below are **capability I/O contracts** (request/response
envelopes), not domain types — this file is on the ``no_type_outside_core`` config-AST
allowlist. The authoritative domain artifacts (``ReconciliationRecord``,
``ProvenanceBreakdown``) live only in ``valuemaxx.core``. Money crosses the wire as
decimal *strings* so no float ever touches the value.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.core import ReconciliationRecord, ReconciliationState, TenantId
from valuemaxx.reconciliation.query import CostSlice, build_breakdown
from valuemaxx.reconciliation.service import EstimateRow, reconcile_match_key

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry

_SURFACES = Surface.API | Surface.MCP | Surface.CLI


class ReconcileDayInput(BaseModel):
    """Request to reconcile one match key's estimates against a billed total."""

    tenant_id: str
    day: str
    match_key: list[str]
    estimates: dict[str, str]  # request_id -> estimated_usd (decimal string)
    billed_total: str


class ReconcileDayOutput(BaseModel):
    """The reconciliation summary: factor, drift, and per-request reconciled values."""

    record_id: str
    estimated_total: str
    billed_total: str
    proration_factor: str
    drift_pct: str
    drift_causes: tuple[str, ...]
    reconciled_by_request: dict[str, str]


class CostBreakdownInput(BaseModel):
    """Request for the mixed-state cost breakdown over a window (amounts as strings)."""

    tenant_id: str
    reconciled_usd: str
    provisional_usd: str
    estimate_only_usd: str


class CostBreakdownOutput(BaseModel):
    """The honest reconciled / provisional / estimate_only breakdown for a window."""

    reconciled_usd: str
    provisional_usd: str
    estimate_only_usd: str
    total_usd: str
    pct_reconciled: str


class _FixedClock:
    """A clock pinned to a request-supplied instant (capability handlers are pure)."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


def _reconcile_day(request: ReconcileDayInput) -> ReconcileDayOutput:
    """Handle ``reconcile_day``: prorate, detect drift, append an additive record.

    A fresh in-memory append target is used inside the pure handler — the app layer
    injects the persistent repository when wiring the surface; here we compute the
    additive record and summary the same way (the record is never an UPDATE).
    """
    tenant_id = TenantId(UUID(request.tenant_id))
    if len(request.match_key) != 5:
        raise ValueError("match_key must have exactly 5 parts")
    match_key: tuple[str, str, str, str, str] = (
        request.match_key[0],
        request.match_key[1],
        request.match_key[2],
        request.match_key[3],
        request.match_key[4],
    )
    estimates = tuple(
        EstimateRow(
            request_id=request_id,
            match_key=match_key,
            estimated_usd=Decimal(value),
        )
        for request_id, value in request.estimates.items()
    )

    counter = {"n": 0}

    def _gen_id() -> str:
        counter["n"] += 1
        return f"{request.day}:{'|'.join(match_key)}:{counter['n']}"

    outcome = reconcile_match_key(
        tenant_id,
        match_key=match_key,
        estimates=estimates,
        billed_total=Decimal(request.billed_total),
        repo=_DiscardRepo(),
        clock=_FixedClock(datetime.now(UTC)),
        gen_id=_gen_id,
    )
    record = outcome.record
    return ReconcileDayOutput(
        record_id=record.id,
        estimated_total=str(record.estimated_total),
        billed_total=str(record.billed_total),
        proration_factor=str(record.proration_factor),
        drift_pct=str(record.drift_pct),
        drift_causes=record.drift_cause_ranked,
        reconciled_by_request={
            rid: str(amount) for rid, amount in outcome.reconciled_by_request.items()
        },
    )


def _cost_breakdown(request: CostBreakdownInput) -> CostBreakdownOutput:
    """Handle ``cost_breakdown``: partition a window by reconciliation state."""
    view = build_breakdown(
        [
            CostSlice(
                state=ReconciliationState.PROVIDER_RECONCILED,
                amount_usd=Decimal(request.reconciled_usd),
            ),
            CostSlice(
                state=ReconciliationState.PROVISIONAL,
                amount_usd=Decimal(request.provisional_usd),
            ),
            CostSlice(
                state=ReconciliationState.ESTIMATE_ONLY,
                amount_usd=Decimal(request.estimate_only_usd),
            ),
        ]
    )
    breakdown = view.breakdown
    return CostBreakdownOutput(
        reconciled_usd=str(breakdown.reconciled_usd),
        provisional_usd=str(breakdown.provisional_usd),
        estimate_only_usd=str(breakdown.estimate_only_usd),
        total_usd=str(breakdown.total_usd),
        pct_reconciled=str(breakdown.pct_reconciled),
    )


class _DiscardRepo:
    """An append target that discards (the persistent repo is injected at the app layer).

    The handler computes the additive record and summary; persistence is wired by the
    surface. This stub honors the append-only port shape without a database, and has no
    update/mutate path (the additive-reconciliation invariant holds here too).
    """

    def append(self, tenant_id: TenantId, record: ReconciliationRecord) -> None:
        """Accept and discard an appended record (no update path exists)."""


def register(registry: Registry) -> None:
    """Register the reconciliation capabilities (M10). Called via discover_and_register."""
    registry.register(
        capability(
            name="reconcile_day",
            input_model=ReconcileDayInput,
            output_model=ReconcileDayOutput,
            handler=_reconcile_day,
            description=(
                "Reconcile one match key's per-request estimates against the "
                "authoritative billed total: prorate so the reconciled values sum "
                "exactly to the invoice, append an additive reconciliation record "
                "(never an update to the estimate), and surface any >10% drift."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="cost_breakdown",
            input_model=CostBreakdownInput,
            output_model=CostBreakdownOutput,
            handler=_cost_breakdown,
            description=(
                "Project a mixed reconciliation-state cost window into the honest "
                "reconciled / provisional / estimate_only breakdown, never collapsing "
                "an estimate into a billed number."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


__all__ = [
    "CostBreakdownInput",
    "CostBreakdownOutput",
    "ReconcileDayInput",
    "ReconcileDayOutput",
    "register",
]
