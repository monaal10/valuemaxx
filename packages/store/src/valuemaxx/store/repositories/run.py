"""PgRunRepository — the concrete async store for :class:`~valuemaxx.core.run.Run`.

Fulfils the :class:`~valuemaxx.core.repositories.RunRepository` contract. The core
ABC is declared with *synchronous* method signatures (a frozen foundation choice);
the real storage layer is async SQLAlchemy, so the concrete repo is registered as a
*virtual* subclass via ``RunRepository.register`` rather than nominally subclassed —
that keeps ``issubclass``/``isinstance`` true and the tenant_id-first contract intact
without falsely claiming a sync-vs-async-compatible override. Every read routes through
:func:`~valuemaxx.store.tenant_guard.require_tenant`, so the tenant scope is structural;
``upsert`` is idempotent on the run id (M7); ``list_by_entity`` matches a run whose
stored entity-key set contains the requested pair.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from valuemaxx.core.repositories import RunRepository
from valuemaxx.store import mappers
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import run as run_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.ids import RunId, TenantId
    from valuemaxx.core.run import Run


class PgRunRepository(BaseRepository):
    """Async SQLAlchemy persistence for runs (virtual ``RunRepository``)."""

    async def upsert(self, tenant_id: TenantId, run: Run) -> None:
        """Insert or update a run (idempotent on the run id)."""
        values = mappers.run_to_row(tenant_id, run)
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, run_table, values, ["tenant_id", "id"]))

    async def get(self, tenant_id: TenantId, run_id: RunId) -> Run | None:
        """Fetch a run by id within the tenant scope, or None."""
        stmt = require_tenant(select(run_table), tenant_id, run_table).where(
            run_table.c.id == run_id
        )
        async with self._sessions() as session:
            row = (await session.execute(stmt)).mappings().one_or_none()
        return mappers.row_to_run(as_row(row)) if row is not None else None

    async def list_by_entity(
        self, tenant_id: TenantId, entity_key: tuple[str, str]
    ) -> Sequence[Run]:
        """List runs (within the tenant) carrying the given entity key."""
        stmt = require_tenant(select(run_table), tenant_id, run_table)
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        runs = [mappers.row_to_run(as_row(row)) for row in rows]
        return [r for r in runs if entity_key in r.entity_keys]


RunRepository.register(PgRunRepository)

__all__ = ["PgRunRepository"]
