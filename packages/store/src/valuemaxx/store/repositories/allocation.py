"""PgAllocationRepository — per-run allocation lines + the H7-carrying rollup (§5.4).

Fulfils :class:`~valuemaxx.core.repositories.AllocationRepository` (virtual subclass).
``upsert_lines`` *replaces* the lines for a run (delete-then-insert, preserving order
via an ordinal); ``list_for_run`` returns them in order; ``get_rollup`` returns the
stored :class:`~valuemaxx.core.allocation.AllocatedRollup`, whose nested H7 confidence
and provenance breakdown round-trip via a JSON payload.

The core ABC has no rollup-write method (it only takes lines), so this concrete repo
adds :meth:`upsert_rollup` to persist the computed rollup; ``get_rollup`` reads it back.
The rollup is stored as one JSON document because its ``confidence`` (minimum_tier +
confidence_distribution) and ``provenance_breakdown`` must serialize together — never
collapsed — exactly as the honesty invariants require.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from valuemaxx.core.allocation import AllocatedLine, AllocatedRollup
from valuemaxx.core.repositories import AllocationRepository
from valuemaxx.store import mappers
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import allocation_line as line_table
from valuemaxx.store.tables import allocation_rollup as rollup_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.ids import RunId, TenantId

_ROLLUP_CONFLICT_KEY = ["tenant_id", "run_id"]


class PgAllocationRepository(BaseRepository):
    """Async persistence for allocation lines + rollup (virtual ``AllocationRepository``)."""

    async def upsert_lines(
        self, tenant_id: TenantId, run_id: RunId, lines: Sequence[object]
    ) -> None:
        """Replace the allocation lines for a run (delete existing, insert the new set)."""
        rows = [
            mappers.allocation_line_to_row(tenant_id, run_id, ordinal, _as_line(line))
            for ordinal, line in enumerate(lines)
        ]
        async with self._sessions.begin() as session:
            await session.execute(
                delete(line_table)
                .where(line_table.c.tenant_id == tenant_id)
                .where(line_table.c.run_id == run_id)
            )
            if rows:
                await session.execute(line_table.insert(), rows)

    async def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[AllocatedLine]:
        """List the allocation lines for a run, in their stored order."""
        stmt = (
            require_tenant(select(line_table), tenant_id, line_table)
            .where(line_table.c.run_id == run_id)
            .order_by(line_table.c.ordinal)
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [mappers.row_to_allocation_line(as_row(row)) for row in rows]

    async def upsert_rollup(self, tenant_id: TenantId, rollup: AllocatedRollup) -> None:
        """Persist the per-run allocation rollup (carries pct_unallocated + H7 confidence)."""
        values: dict[str, object] = {
            "run_id": rollup.run_id,
            "tenant_id": tenant_id,
            "payload": rollup.model_dump(mode="json"),
        }
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, rollup_table, values, _ROLLUP_CONFLICT_KEY))

    async def get_rollup(self, tenant_id: TenantId, run_id: RunId) -> AllocatedRollup | None:
        """Fetch the allocation rollup for a run (pct_unallocated + H7), or None."""
        stmt = require_tenant(select(rollup_table.c.payload), tenant_id, rollup_table).where(
            rollup_table.c.run_id == run_id
        )
        async with self._sessions() as session:
            row = (await session.execute(stmt)).one_or_none()
        if row is None:
            return None
        # strict=False because the JSON payload carries Decimals/enums as strings; the
        # core model is strict on direct construction but we are rehydrating a doc we
        # ourselves serialized with model_dump(mode="json").
        return AllocatedRollup.model_validate(row[0], strict=False)


def _as_line(value: object) -> AllocatedLine:
    """Narrow an ``upsert_lines`` element (typed ``object`` by the ABC) to AllocatedLine."""
    assert isinstance(value, AllocatedLine), "allocation lines must be AllocatedLine instances"
    return value


AllocationRepository.register(PgAllocationRepository)

__all__ = ["PgAllocationRepository"]
