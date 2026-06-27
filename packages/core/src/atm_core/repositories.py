"""Repository ABCs — the storage port, with structural tenant scoping (§3.2).

Every abstract method takes ``tenant_id: TenantId`` as its **mandatory first
parameter** (after ``self``). There is no API to query without a tenant scope, so
isolation is structural, not disciplinary (asserted by ``test_every_repo_method_
tenant_id_first`` and the ``tenant_scoping`` conformance rule).

The :class:`ReconciliationRepository` is **append-only** by design: it exposes
``append`` and ``list_for_match_key`` and has no update/mutate path, because
reconciliation is an additive ``ReconciliationRecord`` and never an UPDATE to the
estimate (§5.3).

The C3 interfaces named at this task (``OutcomesPredicateValidator``,
``SignalClassMapper``, ``ReviewQueue``) get their full bodies at G1; minimal
stubs live here so downstream type references resolve.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # These names appear only in abstract method annotations, which are never
    # evaluated at runtime (ABCs do not validate), so importing them lazily keeps
    # the runtime import graph minimal without breaking any type reference.
    from collections.abc import Sequence
    from datetime import datetime

    from atm_core.attribution import AttributionResult
    from atm_core.cost import CostEvent
    from atm_core.ids import OutcomeEventId, RunId, TenantId
    from atm_core.outcome import OutcomeEvent
    from atm_core.reconciliation import ReconciliationRecord
    from atm_core.run import Run


class RunRepository(ABC):
    """Persistence for :class:`~atm_core.run.Run` records."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, run: Run) -> None:
        """Insert or update a run (idempotent on run id)."""

    @abstractmethod
    def get(self, tenant_id: TenantId, run_id: RunId) -> Run | None:
        """Fetch a run by id within the tenant scope, or None."""

    @abstractmethod
    def list_by_entity(self, tenant_id: TenantId, entity_key: tuple[str, str]) -> Sequence[Run]:
        """List runs that carry the given entity key (for entity-match binding)."""


class CostEventRepository(ABC):
    """Persistence for :class:`~atm_core.cost.CostEvent` records (M7 upsert)."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        """Upsert-on-conflict by idempotency key so double-delivery never double-counts."""

    @abstractmethod
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        """List all cost events for a run."""

    @abstractmethod
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        """List cost events whose occurred_at falls in [start, end)."""


class OutcomeEventRepository(ABC):
    """Persistence for :class:`~atm_core.outcome.OutcomeEvent` records."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, event: OutcomeEvent) -> None:
        """Upsert-on-conflict by idempotency key."""

    @abstractmethod
    def get(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> OutcomeEvent | None:
        """Fetch an outcome by id within the tenant scope, or None."""

    @abstractmethod
    def retract(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> None:
        """Flip a confirmed outcome to retracted (confirmed->retracted only, H8)."""

    @abstractmethod
    def list_unbound(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        """List outcomes not yet bound to a run (the attribution work queue)."""


class AttributionResultRepository(ABC):
    """Persistence for :class:`~atm_core.attribution.AttributionResult` records."""

    @abstractmethod
    def upsert(self, tenant_id: TenantId, result: AttributionResult) -> None:
        """Insert or update an attribution result."""

    @abstractmethod
    def get_for_outcome(
        self, tenant_id: TenantId, outcome_id: OutcomeEventId
    ) -> AttributionResult | None:
        """Fetch the attribution result for an outcome, or None."""


class ReconciliationRepository(ABC):
    """Append-only persistence for :class:`~atm_core.reconciliation.ReconciliationRecord`.

    There is deliberately NO update/mutate/replace method: reconciliation is
    additive and never an UPDATE to an estimate (§5.3).
    """

    @abstractmethod
    def append(self, tenant_id: TenantId, record: ReconciliationRecord) -> None:
        """Append a reconciliation record (additive; never updates an estimate)."""

    @abstractmethod
    def list_for_match_key(
        self, tenant_id: TenantId, match_key: tuple[str, str, str, str, str]
    ) -> Sequence[ReconciliationRecord]:
        """List all reconciliation records for a match key."""


class AllocationRepository(ABC):
    """Persistence for allocated-line records keyed by run."""

    @abstractmethod
    def upsert_lines(
        self,
        tenant_id: TenantId,
        run_id: RunId,
        lines: Sequence[object],
    ) -> None:
        """Replace the allocation lines for a run (the line model lands at G2-ALLOC)."""

    @abstractmethod
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[object]:
        """List the allocation lines for a run."""


class RawRecordRepository(ABC):
    """Persistence for raw record JSON (inference matching + replay, §9)."""

    @abstractmethod
    def put(
        self,
        tenant_id: TenantId,
        record_id: str,
        payload: object,
        entity_keys: frozenset[tuple[str, str]],
    ) -> None:
        """Store a raw record JSON payload with its entity keys."""

    @abstractmethod
    def get(self, tenant_id: TenantId, record_id: str) -> object | None:
        """Fetch a raw record by id, or None."""

    @abstractmethod
    def erase_by_entity(self, tenant_id: TenantId, entity_key: tuple[str, str]) -> int:
        """Erase all raw records carrying an entity key (GDPR/CCPA erasure, H10).

        Returns the number of records erased.
        """


__all__ = [
    "AllocationRepository",
    "AttributionResultRepository",
    "CostEventRepository",
    "OutcomeEventRepository",
    "RawRecordRepository",
    "ReconciliationRepository",
    "RunRepository",
]
