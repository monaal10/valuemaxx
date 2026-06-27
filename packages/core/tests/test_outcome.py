"""F0-CORE-1b: OutcomeBinding + OutcomeEvent — signal-classed, dedup-keyed."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from valuemaxx.core.enums import BindingTier, SignalClass
from valuemaxx.core.ids import CorrelationId, OutcomeEventId, RunId, TenantId
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent


def _tenant() -> TenantId:
    return TenantId(uuid4())


def _event(**overrides: object) -> OutcomeEvent:
    base: dict[str, object] = {
        "tenant_id": _tenant(),
        "id": OutcomeEventId("oe-1"),
        "name": "loan_funded",
        "signal_class": SignalClass.OUTCOME_CONFIRMED,
        "value": Decimal("1000.00"),
        "occurred_at": datetime.now(tz=UTC),
        "binding": OutcomeBinding(run_id=None, tier=None, bound_by=None),
        "entity_keys": frozenset({("application_id", "a-1")}),
        "correlation_id": None,
        "source": "myapp",
        "raw": {},
    }
    base.update(overrides)
    return OutcomeEvent(**base)  # type: ignore[arg-type]


def test_unbound_binding_allows_none() -> None:
    """T-BND-1: an unbound OutcomeBinding has all nullable fields None."""
    binding = OutcomeBinding(run_id=None, tier=None, bound_by=None)
    assert binding.run_id is None
    assert binding.tier is None
    assert binding.bound_by is None


def test_bound_binding() -> None:
    binding = OutcomeBinding(run_id=RunId("run-1"), tier=BindingTier.EXACT, bound_by="t1")
    assert binding.run_id == RunId("run-1")
    assert binding.tier is BindingTier.EXACT


def test_idempotency_prefers_correlation_id() -> None:
    """T-OE-1: dedup key prefers correlation_id when present (§5.2)."""
    ev = _event(correlation_id=CorrelationId("corr-9"))
    assert ev.idempotency_key == CorrelationId("corr-9")


def test_idempotency_falls_back_to_source_and_id() -> None:
    """T-OE-1b: without correlation_id, dedup key = (source, id)."""
    ev = _event(correlation_id=None)
    assert ev.idempotency_key == ("myapp", OutcomeEventId("oe-1"))


def test_signal_class_required() -> None:
    """T-OE-2: signal_class is a required honesty axis — cannot be omitted."""
    with pytest.raises(ValidationError):
        OutcomeEvent(  # type: ignore[call-arg]
            tenant_id=_tenant(),
            id=OutcomeEventId("oe-1"),
            name="x",
            value=None,
            occurred_at=datetime.now(tz=UTC),
            binding=OutcomeBinding(run_id=None, tier=None, bound_by=None),
            entity_keys=frozenset(),
            correlation_id=None,
            source="s",
            raw={},
        )


def test_value_may_be_none() -> None:
    ev = _event(value=None)
    assert ev.value is None
