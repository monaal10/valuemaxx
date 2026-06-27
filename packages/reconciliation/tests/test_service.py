"""Reconciliation service — additive true-up that never mutates the estimate (§5.3)."""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from _recon_helpers import (
    TENANT_A,
    FixedClock,
    InMemoryReconciliationRepository,
    SequentialIds,
    utc,
)
from valuemaxx.core import Provenance, ReconciliationRecord
from valuemaxx.reconciliation.proration import prorate
from valuemaxx.reconciliation.service import (
    EstimateRow,
    MatchKey,
    ReconciliationOutcome,
    reconcile_day,
    reconcile_match_key,
)

_KEY: MatchKey = ("anthropic", "p", "claude-sonnet-4", "output", "2026-06-27")
_NOW = utc(2026, 6, 28)


def _row(request_id: str, est: str) -> EstimateRow:
    return EstimateRow(request_id=request_id, match_key=_KEY, estimated_usd=Decimal(est))


def test_reconcile_match_key_appends_one_additive_record() -> None:
    """Reconciling a key appends exactly one additive ReconciliationRecord."""
    repo = InMemoryReconciliationRepository()
    outcome = reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=(_row("a", "10"), _row("b", "30")),
        billed_total=Decimal("60"),
        repo=repo,
        clock=FixedClock(_NOW),
        gen_id=SequentialIds(),
    )
    records = repo.all_records(TENANT_A)
    assert len(records) == 1
    assert isinstance(records[0], ReconciliationRecord)
    assert records[0].billed_total == Decimal("60")
    assert records[0].estimated_total == Decimal("40")
    assert records[0].proration_factor == Decimal("1.5")
    assert isinstance(outcome, ReconciliationOutcome)


def test_per_request_reconciled_values_sum_exactly_to_billed() -> None:
    """The per-request reconciled values sum to the authoritative billed total."""
    repo = InMemoryReconciliationRepository()
    outcome = reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=(_row("a", "10"), _row("b", "20"), _row("c", "30")),
        billed_total=Decimal("66"),
        repo=repo,
        clock=FixedClock(_NOW),
        gen_id=SequentialIds(),
    )
    values = outcome.reconciled_by_request
    assert sum(values.values(), Decimal(0)) == Decimal("66")
    assert values["a"] + values["b"] + values["c"] == Decimal("66")


def test_reconciled_values_match_prorate() -> None:
    """The service's per-request values equal the proration of the estimates."""
    repo = InMemoryReconciliationRepository()
    rows = (_row("a", "10"), _row("b", "20"), _row("c", "30"))
    outcome = reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=rows,
        billed_total=Decimal("66"),
        repo=repo,
        clock=FixedClock(_NOW),
        gen_id=SequentialIds(),
    )
    expected = prorate((Decimal("10"), Decimal("20"), Decimal("30")), Decimal("66"))
    assert tuple(outcome.reconciled_by_request[r.request_id] for r in rows) == expected


def test_record_carries_provider_reconciled_provenance() -> None:
    """The reconciled provenance is provider_reconciled, linked to the record id."""
    repo = InMemoryReconciliationRepository()
    outcome = reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=(_row("a", "10"),),
        billed_total=Decimal("11"),
        repo=repo,
        clock=FixedClock(_NOW),
        gen_id=SequentialIds(),
    )
    assert outcome.provenance.provenance is Provenance.PROVIDER_RECONCILED
    assert outcome.provenance.reconciliation_record_id == repo.all_records(TENANT_A)[0].id


def test_drift_over_threshold_is_recorded_on_outcome() -> None:
    """A >10% drift surfaces a DriftAlert on the outcome (never silently swapped)."""
    repo = InMemoryReconciliationRepository()
    outcome = reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=(_row("a", "100"),),
        billed_total=Decimal("130"),
        repo=repo,
        clock=FixedClock(_NOW),
        gen_id=SequentialIds(),
    )
    assert outcome.drift_alert is not None
    assert outcome.drift_alert.drift_pct == Decimal("30")
    assert repo.all_records(TENANT_A)[0].drift_pct == Decimal("30")


def test_drift_within_threshold_no_alert() -> None:
    """Within +/-10%, no drift alert is raised (it is noise)."""
    repo = InMemoryReconciliationRepository()
    outcome = reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=(_row("a", "100"),),
        billed_total=Decimal("105"),
        repo=repo,
        clock=FixedClock(_NOW),
        gen_id=SequentialIds(),
    )
    assert outcome.drift_alert is None


def test_rereconcile_appends_new_record_old_retained() -> None:
    """A re-reconcile appends a new record; the original is retained (supersede by time)."""
    repo = InMemoryReconciliationRepository()
    gen = SequentialIds()
    reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=(_row("a", "10"),),
        billed_total=Decimal("11"),
        repo=repo,
        clock=FixedClock(utc(2026, 6, 28)),
        gen_id=gen,
    )
    reconcile_match_key(
        TENANT_A,
        match_key=_KEY,
        estimates=(_row("a", "10"),),
        billed_total=Decimal("12"),
        repo=repo,
        clock=FixedClock(utc(2026, 6, 29)),
        gen_id=gen,
    )
    records = repo.list_for_match_key(TENANT_A, _KEY)
    assert len(records) == 2  # both retained, none overwritten
    latest = max(records, key=lambda r: r.created_at)
    assert latest.billed_total == Decimal("12")


def test_reconcile_day_groups_and_reconciles_each_key() -> None:
    """reconcile_day groups estimates by match key and reconciles each independently."""
    repo = InMemoryReconciliationRepository()
    key2 = ("openai", "p", "gpt-5", "output", "2026-06-27")
    rows = (
        EstimateRow(request_id="a", match_key=_KEY, estimated_usd=Decimal("10")),
        EstimateRow(request_id="b", match_key=key2, estimated_usd=Decimal("5")),
        EstimateRow(request_id="c", match_key=_KEY, estimated_usd=Decimal("30")),
    )
    billed = {_KEY: Decimal("60"), key2: Decimal("6")}
    outcomes = reconcile_day(
        TENANT_A,
        estimate_rows=rows,
        billed_totals=billed,
        repo=repo,
        clock=FixedClock(_NOW),
        gen_id=SequentialIds(),
    )
    assert len(outcomes) == 2
    assert len(repo.all_records(TENANT_A)) == 2
    by_key = {o.record.match_key: o for o in outcomes}
    assert sum(by_key[_KEY].reconciled_by_request.values(), Decimal(0)) == Decimal("60")
    assert sum(by_key[key2].reconciled_by_request.values(), Decimal(0)) == Decimal("6")


def test_service_never_mutates_an_estimate() -> None:
    """AST guard: the service module never calls an update/mutate path on a cost repo.

    Reconciliation is additive (an appended ReconciliationRecord); the service must
    never call ``.update``/``.mutate``/``.replace`` on any repository — the estimate
    (CostEvent) is immutable.
    """
    source = (
        Path(__file__).resolve().parents[1] / "src" / "valuemaxx" / "reconciliation" / "service.py"
    ).read_text()
    tree = ast.parse(source)
    forbidden = {"update", "mutate", "replace", "overwrite", "patch", "set_cost"}
    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (called_attrs & forbidden), (
        f"service calls a forbidden mutate path: {called_attrs & forbidden}"
    )
