"""PgOutcomeEventRepository — correlation upsert, retraction, the unbound work queue.

Fulfils :class:`~valuemaxx.core.repositories.OutcomeEventRepository` (virtual subclass).
``upsert`` is idempotent on the outcome id; ``retract`` enforces the honesty rule that
only a *confirmed* outcome flips to ``outcome_retracted`` (H8) — it reads the row under
a row lock, raises ``ValueError`` if the outcome is missing or not confirmed, and
otherwise updates the signal class in the same transaction. ``list_unbound`` is the
attribution work queue: outcomes with no run binding yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from valuemaxx.core.enums import SignalClass
from valuemaxx.core.repositories import OutcomeEventRepository
from valuemaxx.store import mappers
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import outcome_event as outcome_event_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.ids import OutcomeEventId, TenantId
    from valuemaxx.core.outcome import OutcomeEvent

_CONFLICT_KEY = ["tenant_id", "id"]


class PgOutcomeEventRepository(BaseRepository):
    """Async SQLAlchemy persistence for outcomes (virtual ``OutcomeEventRepository``)."""

    async def upsert(self, tenant_id: TenantId, event: OutcomeEvent) -> None:
        """Upsert an outcome (idempotent on the outcome id)."""
        values = mappers.outcome_event_to_row(tenant_id, event)
        async with self._sessions.begin() as session:
            await session.execute(
                upsert_stmt(session, outcome_event_table, values, _CONFLICT_KEY)
            )

    async def get(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> OutcomeEvent | None:
        """Fetch an outcome by id within the tenant scope, or None."""
        stmt = require_tenant(
            select(outcome_event_table), tenant_id, outcome_event_table
        ).where(outcome_event_table.c.id == outcome_id)
        async with self._sessions() as session:
            row = (await session.execute(stmt)).mappings().one_or_none()
        return mappers.row_to_outcome_event(as_row(row)) if row is not None else None

    async def retract(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> None:
        """Flip a confirmed outcome to retracted (confirmed->retracted only, H8).

        Raises:
            ValueError: if the outcome does not exist in the tenant scope, or its
                signal class is not ``outcome_confirmed`` (only a confirmed outcome
                can be retracted — an attempt or an already-retracted one cannot).
        """
        select_stmt = (
            require_tenant(select(outcome_event_table), tenant_id, outcome_event_table)
            .where(outcome_event_table.c.id == outcome_id)
            .with_for_update()
        )
        async with self._sessions.begin() as session:
            row = (await session.execute(select_stmt)).mappings().one_or_none()
            if row is None:
                raise ValueError(f"outcome {outcome_id!r} not found in tenant scope")
            if row["signal_class"] != SignalClass.OUTCOME_CONFIRMED.value:
                raise ValueError(
                    f"only a confirmed outcome can be retracted; "
                    f"{outcome_id!r} is {row['signal_class']!r}"
                )
            await session.execute(
                update(outcome_event_table)
                .where(outcome_event_table.c.tenant_id == tenant_id)
                .where(outcome_event_table.c.id == outcome_id)
                .values(signal_class=SignalClass.OUTCOME_RETRACTED.value)
            )

    async def list_unbound(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        """List outcomes not yet bound to a run (the attribution work queue)."""
        stmt = require_tenant(
            select(outcome_event_table), tenant_id, outcome_event_table
        ).where(outcome_event_table.c.bound_run_id.is_(None))
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [mappers.row_to_outcome_event(as_row(row)) for row in rows]


OutcomeEventRepository.register(PgOutcomeEventRepository)

__all__ = ["PgOutcomeEventRepository"]
