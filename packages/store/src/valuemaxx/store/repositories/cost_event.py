"""PgCostEventRepository — the concrete async store for CostEvents (M7 upsert).

Fulfils :class:`~valuemaxx.core.repositories.CostEventRepository` (virtual subclass;
see :mod:`valuemaxx.store.repositories.run` for why). ``upsert`` is idempotent on the
``(tenant_id, run_id, attempt_id)`` unique constraint — at-least-once ingest replays
land on the same row and update in place, never double-counting. Reads are
tenant-scoped through :func:`~valuemaxx.store.tenant_guard.require_tenant`;
``list_in_window`` is half-open ``[start, end)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from valuemaxx.core.repositories import CostEventRepository
from valuemaxx.store import mappers
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import cost_event as cost_event_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from valuemaxx.core.cost import CostEvent
    from valuemaxx.core.ids import RunId, TenantId

_IDEMPOTENCY_KEY = ["tenant_id", "run_id", "attempt_id"]


class PgCostEventRepository(BaseRepository):
    """Async SQLAlchemy persistence for cost events (virtual ``CostEventRepository``)."""

    async def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        """Upsert on (tenant, run, attempt) so double-delivery never double-counts (M7)."""
        values = mappers.cost_event_to_row(tenant_id, event)
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, cost_event_table, values, _IDEMPOTENCY_KEY))

    async def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        """List all cost events for a run within the tenant scope."""
        stmt = require_tenant(select(cost_event_table), tenant_id, cost_event_table).where(
            cost_event_table.c.run_id == run_id
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [mappers.row_to_cost_event(as_row(row)) for row in rows]

    async def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        """List cost events whose occurred_at falls in the half-open window [start, end)."""
        stmt = (
            require_tenant(select(cost_event_table), tenant_id, cost_event_table)
            .where(cost_event_table.c.occurred_at >= start)
            .where(cost_event_table.c.occurred_at < end)
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [mappers.row_to_cost_event(as_row(row)) for row in rows]


CostEventRepository.register(PgCostEventRepository)

__all__ = ["PgCostEventRepository"]
