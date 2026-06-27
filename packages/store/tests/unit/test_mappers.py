"""mappers — every core model round-trips through its row representation losslessly.

The mappers are the boundary between the pydantic domain models (frozen, strict) and
the flat SQLAlchemy rows. A round-trip (model -> row dict -> model) must reproduce the
original exactly, including Decimal money, tz-aware datetimes, the six token classes,
the (de)normalised binding fields, and the frozenset-of-tuple entity keys.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from valuemaxx.core.attribution import AttributionCandidate, AttributionResult
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import (
    BindingTier,
    CaptureGranularity,
    Provenance,
    SignalClass,
)
from valuemaxx.core.ids import (
    AttemptId,
    CorrelationId,
    CostEventId,
    OutcomeEventId,
    ReconciliationRecordId,
    RunId,
    TenantId,
)
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.reconciliation import ReconciliationRecord
from valuemaxx.core.run import Run
from valuemaxx.core.tokens import TokenVector
from valuemaxx.store import mappers


def _tenant() -> TenantId:
    return TenantId(uuid4())


def test_run_roundtrips() -> None:
    tenant = _tenant()
    model = Run(
        tenant_id=tenant,
        id=RunId("run-1"),
        agent_name="support-bot",
        started_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
        ended_at=None,
        entity_keys=frozenset({("ticket", "T-1"), ("customer", "C-9")}),
    )
    row = mappers.run_to_row(tenant, model)
    assert mappers.row_to_run(row) == model


def test_cost_event_roundtrips_with_decimal_and_tokens() -> None:
    tenant = _tenant()
    model = CostEvent(
        tenant_id=tenant,
        id=CostEventId("ce-1"),
        run_id=RunId("run-1"),
        attempt_id=AttemptId("att-1"),
        provider="anthropic",
        model="claude-opus-4",
        tokens=TokenVector(
            input_uncached=100,
            cache_read=20,
            cache_write_5m=5,
            cache_write_1h=3,
            output=50,
            reasoning=10,
        ),
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=Decimal("0.0123456789"),
        is_streaming=True,
        partial_recovered=False,
        billing_uncertain_abort=False,
        provenance_warnings=("late_usage",),
        occurred_at=datetime(2026, 6, 27, 12, 1, tzinfo=UTC),
    )
    row = mappers.cost_event_to_row(tenant, model)
    assert mappers.row_to_cost_event(row) == model


def test_cost_event_none_cost_roundtrips() -> None:
    tenant = _tenant()
    model = CostEvent(
        tenant_id=tenant,
        id=CostEventId("ce-2"),
        run_id=RunId("run-1"),
        attempt_id=AttemptId("att-2"),
        provider="bedrock",
        model="claude-3",
        tokens=TokenVector(
            input_uncached=0,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=0,
            reasoning=0,
        ),
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.ESTIMATED),
        cost_usd=None,
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=True,
        provenance_warnings=(),
        occurred_at=datetime(2026, 6, 27, 12, 2, tzinfo=UTC),
    )
    row = mappers.cost_event_to_row(tenant, model)
    restored = mappers.row_to_cost_event(row)
    assert restored.cost_usd is None
    assert restored == model


def test_outcome_event_roundtrips() -> None:
    tenant = _tenant()
    model = OutcomeEvent(
        tenant_id=tenant,
        id=OutcomeEventId("oe-1"),
        name="loan_funded",
        signal_class=SignalClass.OUTCOME_CONFIRMED,
        value=Decimal("50000.00"),
        occurred_at=datetime(2026, 6, 27, 12, 3, tzinfo=UTC),
        binding=OutcomeBinding(
            run_id=RunId("run-1"), tier=BindingTier.EXACT, bound_by="correlation"
        ),
        entity_keys=frozenset({("application", "A-1")}),
        correlation_id=CorrelationId("corr-1"),
        source="webhook",
        raw={"amount": 50000, "nested": {"k": [1, 2, 3]}},
    )
    row = mappers.outcome_event_to_row(tenant, model)
    assert mappers.row_to_outcome_event(row) == model


def test_attribution_result_roundtrips() -> None:
    tenant = _tenant()
    model = AttributionResult(
        tenant_id=tenant,
        outcome_id=OutcomeEventId("oe-1"),
        run_id=RunId("run-1"),
        tier=BindingTier.DETERMINISTIC,
        bound_by="correlation",
        candidates=(
            AttributionCandidate(
                run_id=RunId("run-1"),
                tier=BindingTier.DETERMINISTIC,
                score=0.9,
                rationale="correlation id match",
            ),
        ),
        review_required=False,
    )
    row = mappers.attribution_result_to_row(tenant, model)
    assert mappers.row_to_attribution_result(row) == model


def test_reconciliation_record_roundtrips() -> None:
    tenant = _tenant()
    model = ReconciliationRecord(
        tenant_id=tenant,
        id=ReconciliationRecordId("rr-1"),
        match_key=("anthropic", "proj-1", "claude-opus-4", "output", "2026-06-27"),
        estimated_total=Decimal("100.1234567890"),
        billed_total=Decimal("102.0000000000"),
        proration_factor=Decimal("1.0188000000"),
        drift_pct=Decimal("1.8800000000"),
        drift_cause_ranked=("negotiated_rate", "cache_mispricing"),
        created_at=datetime(2026, 6, 27, 0, 0, tzinfo=UTC),
    )
    row = mappers.reconciliation_record_to_row(tenant, model)
    assert mappers.row_to_reconciliation_record(row) == model
