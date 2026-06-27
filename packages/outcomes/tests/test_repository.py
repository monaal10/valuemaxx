"""The in-memory OutcomeEventRepository stub used by this package's unit/integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from valuemaxx.core import (
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    OutcomeEventRepository,
    SignalClass,
    TenantId,
)
from valuemaxx.outcomes.repository import InMemoryOutcomeEventRepository

_TENANT = TenantId(uuid4())
_OTHER_TENANT = TenantId(uuid4())


def _event(name: str, *, signal: SignalClass = SignalClass.OUTCOME_CONFIRMED) -> OutcomeEvent:
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


def test_repo_is_a_core_subclass() -> None:
    """The stub implements the core ABC (so callers depend only on the interface)."""
    assert isinstance(InMemoryOutcomeEventRepository(), OutcomeEventRepository)


def test_upsert_then_get() -> None:
    """An upserted event is retrievable by id within its tenant scope."""
    repo = InMemoryOutcomeEventRepository()
    event = _event("e1")
    repo.upsert(_TENANT, event)
    assert repo.get(_TENANT, OutcomeEventId("e1")) == event


def test_upsert_is_idempotent_by_idempotency_key() -> None:
    """Re-upserting the same idempotency key does not duplicate the stored event."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1"))
    repo.upsert(_TENANT, _event("e1"))
    assert len(repo.all_for_tenant(_TENANT)) == 1


def test_get_is_tenant_scoped() -> None:
    """An event stored under one tenant is invisible to another."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1"))
    assert repo.get(_OTHER_TENANT, OutcomeEventId("e1")) is None


def test_list_unbound_returns_only_unbound() -> None:
    """list_unbound returns events whose binding has no run_id."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1"))
    unbound = repo.list_unbound(_TENANT)
    assert [e.id for e in unbound] == [OutcomeEventId("e1")]


def test_retract_flips_confirmed_to_retracted() -> None:
    """retract flips a confirmed outcome to retracted (confirmed->retracted only)."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1", signal=SignalClass.OUTCOME_CONFIRMED))
    repo.retract(_TENANT, OutcomeEventId("e1"))
    stored = repo.get(_TENANT, OutcomeEventId("e1"))
    assert stored is not None
    assert stored.signal_class is SignalClass.OUTCOME_RETRACTED


def test_retract_only_affects_confirmed() -> None:
    """retract is a no-op on a non-confirmed outcome (status guard)."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1", signal=SignalClass.ACTION_ATTEMPTED))
    repo.retract(_TENANT, OutcomeEventId("e1"))
    stored = repo.get(_TENANT, OutcomeEventId("e1"))
    assert stored is not None
    assert stored.signal_class is SignalClass.ACTION_ATTEMPTED


def test_retract_missing_is_noop() -> None:
    """Retracting an unknown id is a no-op (idempotent, never raises)."""
    repo = InMemoryOutcomeEventRepository()
    repo.retract(_TENANT, OutcomeEventId("nope"))  # must not raise


def test_get_missing_returns_none() -> None:
    """Fetching an unknown id within a known tenant returns None."""
    repo = InMemoryOutcomeEventRepository()
    repo.upsert(_TENANT, _event("e1"))
    assert repo.get(_TENANT, OutcomeEventId("missing")) is None


def test_failing_repo_raises_on_every_method() -> None:
    """Every method of the failing variant raises (drives fail-open coverage)."""
    from valuemaxx.outcomes.repository import FailingOutcomeEventRepository

    repo = FailingOutcomeEventRepository()
    with pytest.raises(RuntimeError):
        repo.upsert(_TENANT, _event("e1"))
    with pytest.raises(RuntimeError):
        repo.get(_TENANT, OutcomeEventId("e1"))
    with pytest.raises(RuntimeError):
        repo.retract(_TENANT, OutcomeEventId("e1"))
    with pytest.raises(RuntimeError):
        repo.list_unbound(_TENANT)
