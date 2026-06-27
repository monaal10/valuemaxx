"""In-memory :class:`~valuemaxx.core.OutcomeEventRepository` stubs for this package's tests.

The real persistence adapter lives in ``valuemaxx.store`` (G2-STORE) — which this
package must **not** import (``dependency_direction``). For unit/integration tests in
``outcomes`` we depend only on the core ABC and supply an in-memory implementation.
Storage is keyed by the event's :attr:`~valuemaxx.core.OutcomeEvent.idempotency_key`
so a double delivery never double-counts, and is structurally tenant-scoped.

:class:`FailingOutcomeEventRepository` always raises on write; it exists to prove the
emitter fails open (never propagates a repo error into the instrumented host call).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override  # py3.11 target: typing.override is 3.12+
from valuemaxx.core import OutcomeEventRepository, SignalClass

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core import OutcomeEvent, OutcomeEventId, TenantId

# The idempotency key is either a CorrelationId (str) or a (source, id) tuple.
_IdemKey = str | tuple[str, "OutcomeEventId"]


class InMemoryOutcomeEventRepository(OutcomeEventRepository):
    """A dict-backed outcome repository, tenant-scoped and idempotent on the dedup key."""

    def __init__(self) -> None:
        # tenant_id -> idempotency_key -> event
        self._by_tenant: dict[TenantId, dict[_IdemKey, OutcomeEvent]] = {}

    @override
    def upsert(self, tenant_id: TenantId, event: OutcomeEvent) -> None:
        """Insert or replace by idempotency key (double-delivery never duplicates)."""
        self._by_tenant.setdefault(tenant_id, {})[event.idempotency_key] = event

    @override
    def get(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> OutcomeEvent | None:
        """Fetch by id within the tenant scope, or None."""
        for event in self._by_tenant.get(tenant_id, {}).values():
            if event.id == outcome_id:
                return event
        return None

    @override
    def retract(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> None:
        """Flip a confirmed outcome to retracted (confirmed->retracted only, H8)."""
        scope = self._by_tenant.get(tenant_id, {})
        for key, event in scope.items():
            if event.id != outcome_id:
                continue
            if event.signal_class is SignalClass.OUTCOME_CONFIRMED:
                scope[key] = event.model_copy(
                    update={"signal_class": SignalClass.OUTCOME_RETRACTED}
                )
            return

    @override
    def list_unbound(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        """List outcomes not yet bound to a run (binding.run_id is None)."""
        return tuple(
            event
            for event in self._by_tenant.get(tenant_id, {}).values()
            if event.binding.run_id is None
        )

    def all_for_tenant(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        """Every stored event for a tenant (test helper, not part of the core ABC)."""
        return tuple(self._by_tenant.get(tenant_id, {}).values())


class FailingOutcomeEventRepository(OutcomeEventRepository):
    """A repository whose every method raises — used to prove the emitter fails open."""

    @override
    def upsert(self, tenant_id: TenantId, event: OutcomeEvent) -> None:
        """Always raise (the emitter must catch this and never re-raise into the host)."""
        raise RuntimeError("simulated storage failure")

    @override
    def get(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> OutcomeEvent | None:
        """Always raise."""
        raise RuntimeError("simulated storage failure")

    @override
    def retract(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> None:
        """Always raise."""
        raise RuntimeError("simulated storage failure")

    @override
    def list_unbound(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        """Always raise."""
        raise RuntimeError("simulated storage failure")


__all__ = ["FailingOutcomeEventRepository", "InMemoryOutcomeEventRepository"]
