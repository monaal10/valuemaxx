"""In-memory repository stubs for metrics executor tests.

These implement the ``valuemaxx.core`` repository ABCs against in-memory dicts so
the executor can be tested without ``valuemaxx.store`` (real Postgres wiring is
G5, H6). They are tenant-scoped exactly like the real repos: every method takes
``tenant_id`` first and only returns records for that tenant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override
from valuemaxx.core import (
    CostEvent,
    CostEventRepository,
    OutcomeEvent,
    OutcomeEventId,
    OutcomeEventRepository,
    RunId,
    TenantId,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime


class InMemoryCostEventRepository(CostEventRepository):
    """An in-memory :class:`~valuemaxx.core.CostEventRepository` for tests."""

    def __init__(self) -> None:
        self._by_tenant: dict[TenantId, list[CostEvent]] = {}

    @override
    def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        self._by_tenant.setdefault(tenant_id, []).append(event)

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        return [e for e in self._by_tenant.get(tenant_id, []) if e.run_id == run_id]

    @override
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        return [e for e in self._by_tenant.get(tenant_id, []) if start <= e.occurred_at < end]


class InMemoryOutcomeEventRepository(OutcomeEventRepository):
    """An in-memory :class:`~valuemaxx.core.OutcomeEventRepository` for tests."""

    def __init__(self) -> None:
        self._by_tenant: dict[TenantId, dict[OutcomeEventId, OutcomeEvent]] = {}

    @override
    def upsert(self, tenant_id: TenantId, event: OutcomeEvent) -> None:
        self._by_tenant.setdefault(tenant_id, {})[event.id] = event

    @override
    def get(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> OutcomeEvent | None:
        return self._by_tenant.get(tenant_id, {}).get(outcome_id)

    @override
    def retract(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> None:
        raise NotImplementedError  # not exercised by the executor read path

    @override
    def list_unbound(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        return [o for o in self._by_tenant.get(tenant_id, {}).values() if o.binding.run_id is None]

    def list_all(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        """Test helper: every outcome for the tenant (not part of the ABC)."""
        return list(self._by_tenant.get(tenant_id, {}).values())
