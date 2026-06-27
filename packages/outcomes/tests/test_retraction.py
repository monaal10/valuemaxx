"""OUT-E: retract_outcome — confirmed -> retracted only, idempotent, status-guarded."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from valuemaxx.core import (
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    SignalClass,
    TenantId,
)
from valuemaxx.outcomes.repository import InMemoryOutcomeEventRepository
from valuemaxx.outcomes.retraction import RetractionResult, retract_outcome

_TENANT = TenantId(uuid4())


def _event(name: str, *, signal: SignalClass) -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=_TENANT,
        id=OutcomeEventId(name),
        name=name,
        signal_class=signal,
        value=Decimal("100"),
        occurred_at=datetime(2026, 6, 27, tzinfo=UTC),
        binding=OutcomeBinding(run_id=None, tier=None, bound_by=None),
        entity_keys=frozenset(),
        correlation_id=None,
        source="stripe",
        raw={},
    )


def test_retract_flips_confirmed_to_retracted() -> None:
    """A confirmed outcome flips to retracted."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1", signal=SignalClass.OUTCOME_CONFIRMED))
    result = retract_outcome(repo, tenant_id=_TENANT, outcome_id=OutcomeEventId("e1"))
    assert result is RetractionResult.RETRACTED
    stored = repo.get(_TENANT, OutcomeEventId("e1"))
    assert stored is not None
    assert stored.signal_class is SignalClass.OUTCOME_RETRACTED


def test_retract_is_idempotent() -> None:
    """Retracting an already-retracted outcome is a no-op (idempotent), not an error."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1", signal=SignalClass.OUTCOME_CONFIRMED))
    retract_outcome(repo, tenant_id=_TENANT, outcome_id=OutcomeEventId("e1"))
    result = retract_outcome(repo, tenant_id=_TENANT, outcome_id=OutcomeEventId("e1"))
    assert result is RetractionResult.ALREADY_RETRACTED
    stored = repo.get(_TENANT, OutcomeEventId("e1"))
    assert stored is not None
    assert stored.signal_class is SignalClass.OUTCOME_RETRACTED


def test_retract_only_flips_confirmed_not_attempted() -> None:
    """An action_attempted outcome is never retracted (status guard)."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1", signal=SignalClass.ACTION_ATTEMPTED))
    result = retract_outcome(repo, tenant_id=_TENANT, outcome_id=OutcomeEventId("e1"))
    assert result is RetractionResult.NOT_CONFIRMED
    stored = repo.get(_TENANT, OutcomeEventId("e1"))
    assert stored is not None
    assert stored.signal_class is SignalClass.ACTION_ATTEMPTED


def test_retract_unknown_outcome_reports_not_found() -> None:
    """Retracting an unknown id reports not-found (never raises)."""
    repo = InMemoryOutcomeEventRepository()
    result = retract_outcome(repo, tenant_id=_TENANT, outcome_id=OutcomeEventId("nope"))
    assert result is RetractionResult.NOT_FOUND
