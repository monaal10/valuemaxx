"""PgAttributionResultRepository — one attribution result per (tenant, outcome).

Fulfils :class:`~valuemaxx.core.repositories.AttributionResultRepository` (virtual
subclass). ``upsert`` is idempotent on the outcome id (the natural key); ``get_for_outcome``
is tenant-scoped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from valuemaxx.core.repositories import AttributionResultRepository
from valuemaxx.store import mappers
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import attribution_result as attribution_result_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from valuemaxx.core.attribution import AttributionResult
    from valuemaxx.core.ids import OutcomeEventId, TenantId

_CONFLICT_KEY = ["tenant_id", "outcome_id"]


class PgAttributionResultRepository(BaseRepository):
    """Async persistence for attribution results (virtual ``AttributionResultRepository``)."""

    async def upsert(self, tenant_id: TenantId, result: AttributionResult) -> None:
        """Insert or update the attribution result for an outcome."""
        values = mappers.attribution_result_to_row(tenant_id, result)
        async with self._sessions.begin() as session:
            await session.execute(
                upsert_stmt(session, attribution_result_table, values, _CONFLICT_KEY)
            )

    async def get_for_outcome(
        self, tenant_id: TenantId, outcome_id: OutcomeEventId
    ) -> AttributionResult | None:
        """Fetch the attribution result for an outcome within the tenant scope, or None."""
        stmt = require_tenant(
            select(attribution_result_table), tenant_id, attribution_result_table
        ).where(attribution_result_table.c.outcome_id == outcome_id)
        async with self._sessions() as session:
            row = (await session.execute(stmt)).mappings().one_or_none()
        return mappers.row_to_attribution_result(as_row(row)) if row is not None else None


AttributionResultRepository.register(PgAttributionResultRepository)

__all__ = ["PgAttributionResultRepository"]
