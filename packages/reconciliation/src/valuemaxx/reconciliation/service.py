"""Reconciliation service — the additive true-up orchestrator (§5.3).

Given the per-request *estimates* grouped under a match key and the authoritative
*billed total* for that key, the service:

  1. prorates the billed total across the estimates so the per-request reconciled
     values sum to the billed total exactly (:mod:`valuemaxx.reconciliation.proration`);
  2. classifies the drift and, when it exceeds 10%, surfaces a ranked
     :class:`~valuemaxx.core.DriftAlert` (:mod:`valuemaxx.reconciliation.drift`);
  3. **appends** an additive :class:`~valuemaxx.core.ReconciliationRecord` capturing
     the estimate, the billed total, the proration factor, and the drift.

The estimate is **immutable**: the service NEVER updates a ``CostEvent`` (there is no
such method on the append-only repos, and an AST test guards against any
``update``/``mutate`` call). Re-reconciling a window appends *new* records that
supersede prior ones by ``created_at``; the originals are retained for audit.

``EstimateRow`` and ``ReconciliationOutcome`` are plain frozen dataclasses (not
domain models) — the authoritative domain artifact is the appended
:class:`~valuemaxx.core.ReconciliationRecord`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from valuemaxx.core import (
    DriftAlert,
    Provenance,
    ProvenanceLabel,
    ReconciliationRecord,
    ReconciliationRecordId,
)
from valuemaxx.reconciliation.drift import classify_drift, drift_pct
from valuemaxx.reconciliation.proration import prorate, proration_factor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from valuemaxx.core import Clock, TenantId

MatchKey = tuple[str, str, str, str, str]


@runtime_checkable
class ReconciliationAppender(Protocol):
    """The append-only write port the service needs (a narrow view of the repo ABC).

    Deliberately exposes *only* ``append`` — the service cannot reach an update/mutate
    path because none exists in its dependency surface. The full
    :class:`~valuemaxx.core.ReconciliationRepository` (also append-only) satisfies this.
    """

    def append(self, tenant_id: TenantId, record: ReconciliationRecord) -> None:
        """Append an additive reconciliation record (never an update)."""
        ...


@dataclass(frozen=True, slots=True)
class EstimateRow:
    """One per-request provisional cost estimate, tagged with its match key.

    A plain frozen dataclass: the input the service prorates. ``request_id``
    identifies the request whose reconciled value is returned in the outcome.
    """

    request_id: str
    match_key: MatchKey
    estimated_usd: Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    """The result of reconciling one match key (NOT a domain model).

    Attributes:
        record: the additive :class:`~valuemaxx.core.ReconciliationRecord` appended.
        reconciled_by_request: per-request reconciled value, summing exactly to the
            billed total. This is the *display* reconciliation — it never mutates the
            immutable estimate.
        provenance: the :class:`~valuemaxx.core.ProvenanceLabel` to stamp on reconciled
            views (``provider_reconciled``, linked to the appended record's id).
        drift_alert: a :class:`~valuemaxx.core.DriftAlert` when drift > 10%, else None.
    """

    record: ReconciliationRecord
    reconciled_by_request: Mapping[str, Decimal]
    provenance: ProvenanceLabel
    drift_alert: DriftAlert | None = field(default=None)


def reconcile_match_key(
    tenant_id: TenantId,
    *,
    match_key: MatchKey,
    estimates: tuple[EstimateRow, ...],
    billed_total: Decimal,
    repo: ReconciliationAppender,
    clock: Clock,
    gen_id: Callable[[], str],
) -> ReconciliationOutcome:
    """Reconcile one match key: prorate, detect drift, append an additive record.

    Args:
        tenant_id: the tenant scope (first, structurally required).
        match_key: the (provider, project, model, token_class, day) tuple.
        estimates: the per-request estimates under this key (at least one).
        billed_total: the authoritative billed total for the key.
        repo: the append-only reconciliation repository.
        clock: the injected clock for ``created_at`` (no ``datetime.now()``).
        gen_id: the injected id generator (no ``uuid4()``).

    Returns:
        The :class:`ReconciliationOutcome` for the key, with the appended record,
        the per-request reconciled values, the provenance label, and any drift alert.

    Raises:
        ValueError: if ``estimates`` is empty, or sums to zero with a non-zero billed
            total (propagated from :func:`~valuemaxx.reconciliation.proration.prorate`).
    """
    estimated_total = sum((row.estimated_usd for row in estimates), Decimal(0))
    shares = prorate(tuple(row.estimated_usd for row in estimates), billed_total)
    reconciled_by_request = {
        row.request_id: share for row, share in zip(estimates, shares, strict=True)
    }
    factor = proration_factor(tuple(row.estimated_usd for row in estimates), billed_total)
    drift = classify_drift(match_key, estimated=estimated_total, billed=billed_total)
    signed_drift = drift_pct(estimated_total, billed_total)

    record_id = ReconciliationRecordId(gen_id())
    record = ReconciliationRecord(
        tenant_id=tenant_id,
        id=record_id,
        match_key=match_key,
        estimated_total=estimated_total,
        billed_total=billed_total,
        proration_factor=factor,
        drift_pct=signed_drift,
        drift_cause_ranked=drift.ranked_causes if drift is not None else (),
        created_at=clock.now(),
    )
    repo.append(tenant_id, record)

    provenance = ProvenanceLabel(
        provenance=Provenance.PROVIDER_RECONCILED,
        reconciliation_record_id=record_id,
    )
    return ReconciliationOutcome(
        record=record,
        reconciled_by_request=reconciled_by_request,
        provenance=provenance,
        drift_alert=drift,
    )


def reconcile_day(
    tenant_id: TenantId,
    *,
    estimate_rows: Iterable[EstimateRow],
    billed_totals: Mapping[MatchKey, Decimal],
    repo: ReconciliationAppender,
    clock: Clock,
    gen_id: Callable[[], str],
) -> tuple[ReconciliationOutcome, ...]:
    """Reconcile a whole day: group estimates by match key and reconcile each.

    Estimate rows whose match key has no billed total are skipped (nothing to
    reconcile against yet — they stay provisional). Each reconciled key appends its
    own additive record.

    Args:
        tenant_id: the tenant scope (first, structurally required).
        estimate_rows: every per-request estimate in the window.
        billed_totals: the authoritative billed total per match key.
        repo: the append-only reconciliation repository.
        clock: the injected clock.
        gen_id: the injected id generator.

    Returns:
        One :class:`ReconciliationOutcome` per match key that had a billed total.
    """
    grouped: dict[MatchKey, list[EstimateRow]] = {}
    for row in estimate_rows:
        grouped.setdefault(row.match_key, []).append(row)

    outcomes: list[ReconciliationOutcome] = []
    for match_key, rows in grouped.items():
        billed = billed_totals.get(match_key)
        if billed is None:
            continue
        outcomes.append(
            reconcile_match_key(
                tenant_id,
                match_key=match_key,
                estimates=tuple(rows),
                billed_total=billed,
                repo=repo,
                clock=clock,
                gen_id=gen_id,
            )
        )
    return tuple(outcomes)


__all__ = [
    "EstimateRow",
    "MatchKey",
    "ReconciliationAppender",
    "ReconciliationOutcome",
    "reconcile_day",
    "reconcile_match_key",
]
