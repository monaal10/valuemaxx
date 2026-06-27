"""OUT-B: OutcomeEmitter.emit — signal via mapper, idempotency, non-blocking fail-open."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from valuemaxx.core import RunId, SignalClass, TenantId
from valuemaxx.outcomes.instrument.emitter import EmitRequest, OutcomeEmitter
from valuemaxx.outcomes.repository import (
    FailingOutcomeEventRepository,
    InMemoryOutcomeEventRepository,
)
from valuemaxx.outcomes.signal import SystemSignalClassMapper

_TENANT = TenantId(uuid4())


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


class _SeqUuid:
    def __init__(self) -> None:
        self._n = 0

    def new(self) -> str:
        self._n += 1
        return f"outcome-{self._n}"


_AnyRepo = InMemoryOutcomeEventRepository | FailingOutcomeEventRepository


def _emitter(repo: _AnyRepo) -> OutcomeEmitter:
    return OutcomeEmitter(
        repository=repo,
        mapper=SystemSignalClassMapper(),
        clock=_FixedClock(),
        uuid_gen=_SeqUuid(),
    )


def _request(**overrides: object) -> EmitRequest:
    base: dict[str, object] = {
        "tenant_id": _TENANT,
        "name": "loan_funded",
        "match_kind": "function",
        "declared_signal": SignalClass.OUTCOME_CONFIRMED.value,
        "value": Decimal("1000"),
        "entity_keys": frozenset({("application_id", "app-7")}),
        "correlation_id": None,
        "source": "myapp.loans",
        "run_id": RunId("run-7"),
        "raw": {"status": "funded"},
    }
    base.update(overrides)
    return EmitRequest(**base)  # type: ignore[arg-type]


def test_function_match_cannot_emit_confirmed() -> None:
    """A function match is stored as action_attempted even when confirmed is declared."""
    repo = InMemoryOutcomeEventRepository()
    _emitter(repo).emit(_request(match_kind="function"))
    stored = repo.all_for_tenant(_TENANT)
    assert len(stored) == 1
    assert stored[0].signal_class is SignalClass.ACTION_ATTEMPTED


def test_webhook_match_can_emit_confirmed() -> None:
    """A webhook match honors a declared confirmed signal (authoritative)."""
    repo = InMemoryOutcomeEventRepository()
    _emitter(repo).emit(_request(match_kind="webhook", source="stripe"))
    assert repo.all_for_tenant(_TENANT)[0].signal_class is SignalClass.OUTCOME_CONFIRMED


def test_emit_binds_run_id_from_request() -> None:
    """The emitted event carries the run_id binding when one is supplied."""
    repo = InMemoryOutcomeEventRepository()
    _emitter(repo).emit(_request(run_id=RunId("run-7")))
    event = repo.all_for_tenant(_TENANT)[0]
    assert event.binding.run_id == RunId("run-7")


def test_emit_without_run_id_is_unbound() -> None:
    """With no active run, the emitted event is unbound (binding.run_id is None)."""
    repo = InMemoryOutcomeEventRepository()
    _emitter(repo).emit(_request(run_id=None))
    event = repo.all_for_tenant(_TENANT)[0]
    assert event.binding.run_id is None


def test_emit_is_idempotent_on_correlation_id() -> None:
    """Double-delivery with the same correlation_id stores exactly one event."""
    repo = InMemoryOutcomeEventRepository()
    emitter = _emitter(repo)
    emitter.emit(_request(match_kind="webhook", source="stripe", correlation_id="evt_1"))
    emitter.emit(_request(match_kind="webhook", source="stripe", correlation_id="evt_1"))
    assert len(repo.all_for_tenant(_TENANT)) == 1


def test_emit_carries_value_and_entity_keys() -> None:
    """The compiled value and entity keys are carried onto the event."""
    repo = InMemoryOutcomeEventRepository()
    _emitter(repo).emit(_request(value=Decimal("1000")))
    event = repo.all_for_tenant(_TENANT)[0]
    assert event.value == Decimal("1000")
    assert ("application_id", "app-7") in event.entity_keys


def test_emit_fails_open_on_repository_error() -> None:
    """A repository error is swallowed (logged) — emit never raises into the host."""
    emitter = _emitter(FailingOutcomeEventRepository())
    # must not raise
    emitter.emit(_request())


def test_emit_returns_event_id_on_success_and_none_on_failure() -> None:
    """emit returns the stored event id on success, None when it fails open."""
    ok_repo = InMemoryOutcomeEventRepository()
    assert _emitter(ok_repo).emit(_request()) is not None
    assert _emitter(FailingOutcomeEventRepository()).emit(_request()) is None
