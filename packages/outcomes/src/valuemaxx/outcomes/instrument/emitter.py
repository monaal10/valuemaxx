"""OUT-B: turn a matched outcome into a signal-classed, persisted :class:`OutcomeEvent`.

:class:`OutcomeEmitter` is the one place an :class:`~valuemaxx.core.OutcomeEvent` is
constructed from a match. It is deliberately small and **fails open** (AGENTS.md §5:
the SDK must never crash the host): any error — a repo failure, a bad value — is
logged via the secret-safe logger and dropped, never re-raised into the instrumented
call. The signal class is assigned by the injected
:class:`~valuemaxx.core.SignalClassMapper` (system-owned), never by the caller, so a
function/HTTP match can never be stored as ``outcome_confirmed``.

Time and ids are injected (:class:`~valuemaxx.core.Clock`, :class:`~valuemaxx.core.UuidGen`)
so emission is deterministic under test (no ``datetime.now()`` / ``uuid4()`` in app code).
Idempotency is the event's :attr:`~valuemaxx.core.OutcomeEvent.idempotency_key` — the
round-tripped ``correlation_id`` when present, else ``(source, id)`` — so a double
delivery never double-counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from valuemaxx.core import (
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    SignalClass,
)
from valuemaxx.outcomes.safelog import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping
    from decimal import Decimal

    from valuemaxx.core import (
        Clock,
        CorrelationId,
        OutcomeEventRepository,
        RunId,
        SignalClassMapper,
        TenantId,
        UuidGen,
    )

_logger = get_logger("valuemaxx.outcomes.emitter")


@dataclass(frozen=True, slots=True)
class EmitRequest:
    """The fully-resolved inputs for one outcome emission (a transport object, not a model).

    ``declared_signal`` is the rule's *preference*; the mapper has the final say.
    ``run_id`` is the ambient/echoed run id (or None when unbound). ``value`` and
    ``entity_keys`` are already extracted from the match by the compiled expressions.
    """

    tenant_id: TenantId
    name: str
    match_kind: str
    declared_signal: str
    value: Decimal | None
    entity_keys: frozenset[tuple[str, str]]
    correlation_id: CorrelationId | None
    source: str
    run_id: RunId | None
    raw: Mapping[str, object] = field(default_factory=lambda: {})


class OutcomeEmitter:
    """Builds + persists a signal-classed :class:`OutcomeEvent`, failing open on any error."""

    def __init__(
        self,
        *,
        repository: OutcomeEventRepository,
        mapper: SignalClassMapper,
        clock: Clock,
        uuid_gen: UuidGen,
    ) -> None:
        self._repo = repository
        self._mapper = mapper
        self._clock = clock
        self._uuid = uuid_gen

    def emit(self, request: EmitRequest) -> OutcomeEventId | None:
        """Build, signal-class, and persist an outcome; return its id, or None on failure.

        Never raises: a repository or construction error is logged (secret-safe) and
        swallowed so the instrumented host call is unaffected (fail-open invariant).
        """
        try:
            event = self._build(request)
            self._repo.upsert(request.tenant_id, event)
        except Exception as exc:  # fail-open: the host must never see our internal error
            _logger.warning("outcome emit failed for %r: %s", request.name, exc)
            return None
        return event.id

    def _build(self, request: EmitRequest) -> OutcomeEvent:
        signal = SignalClass(
            self._mapper.map_signal(
                match_kind=request.match_kind, declared=request.declared_signal
            )
        )
        return OutcomeEvent(
            tenant_id=request.tenant_id,
            id=OutcomeEventId(self._uuid.new()),
            name=request.name,
            signal_class=signal,
            value=request.value,
            occurred_at=self._clock.now(),
            binding=OutcomeBinding(run_id=request.run_id, tier=None, bound_by=None),
            entity_keys=request.entity_keys,
            correlation_id=request.correlation_id,
            source=request.source,
            raw=request.raw,
        )


__all__ = ["EmitRequest", "OutcomeEmitter"]
