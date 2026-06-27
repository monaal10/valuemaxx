"""PgRawRecordRepository — JSONB raw payloads for replay + GDPR erasure (§9, H10).

Fulfils :class:`~valuemaxx.core.repositories.RawRecordRepository` (virtual subclass).
``put`` stores the raw record JSON payload *unmodified* (so inference-matching and
replay see exactly what arrived) keyed by ``(tenant_id, record_id)``; ``get`` returns
the payload byte/structure-identical; ``erase_by_entity`` is the GDPR/CCPA delete-by-
entity path (H10) and returns the number of records erased.

Entity-key containment is evaluated in Python after a tenant-scoped load rather than
via a dialect-specific JSON operator, so the erasure path is correct on both Postgres
and SQLite. It is not a hot path (erasure is rare and bounded by tenant), so the load-
filter-delete shape is acceptable and keeps the semantics identical across dialects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from valuemaxx.core.repositories import RawRecordRepository
from valuemaxx.store import mappers
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import raw_record as raw_record_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from valuemaxx.core.ids import TenantId

_CONFLICT_KEY = ["tenant_id", "id"]


class PgRawRecordRepository(BaseRepository):
    """Async persistence for raw JSON records (virtual ``RawRecordRepository``)."""

    async def put(
        self,
        tenant_id: TenantId,
        record_id: str,
        payload: object,
        entity_keys: frozenset[tuple[str, str]],
    ) -> None:
        """Store a raw record JSON payload (unmodified) with its entity keys."""
        values: dict[str, object] = {
            "id": record_id,
            "tenant_id": tenant_id,
            "payload": payload,
            "entity_keys": mappers.entity_keys_to_json(entity_keys),
        }
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, raw_record_table, values, _CONFLICT_KEY))

    async def get(self, tenant_id: TenantId, record_id: str) -> object | None:
        """Fetch a raw record payload by id within the tenant scope, or None."""
        stmt = require_tenant(
            select(raw_record_table.c.payload), tenant_id, raw_record_table
        ).where(raw_record_table.c.id == record_id)
        async with self._sessions() as session:
            row = (await session.execute(stmt)).one_or_none()
        return row[0] if row is not None else None

    async def erase_by_entity(self, tenant_id: TenantId, entity_key: tuple[str, str]) -> int:
        """Erase all raw records carrying an entity key (GDPR/CCPA erasure, H10).

        Returns the number of records erased.
        """
        scan = require_tenant(
            select(raw_record_table.c.id, raw_record_table.c.entity_keys),
            tenant_id,
            raw_record_table,
        )
        async with self._sessions.begin() as session:
            rows = (await session.execute(scan)).mappings().all()
            doomed = [
                as_row(row)["id"]
                for row in rows
                if entity_key in mappers.entity_keys_from_json(as_row(row)["entity_keys"])
            ]
            if not doomed:
                return 0
            await session.execute(
                delete(raw_record_table)
                .where(raw_record_table.c.tenant_id == tenant_id)
                .where(raw_record_table.c.id.in_(doomed))
            )
        return len(doomed)


RawRecordRepository.register(PgRawRecordRepository)

__all__ = ["PgRawRecordRepository"]
