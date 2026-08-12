"""PgEntityAliasRepository — persistence for asserted identity edges.

Follows the same shape as the other repos: tenant scope is structural via
:func:`~valuemaxx.store.tenant_guard.require_tenant`, and `append` is idempotent on
the edge itself rather than on a generated id. Asserting `session→lead` twice is one
claim; letting a retry write a second row would multiply the edges the closure walks
without changing what is true.

There is no update or delete path. An alias is an assertion that two keys were always
the same entity, so retracting one would silently re-orphan history that has already
been costed. If a claim turns out to be wrong, that is a correction worth making
explicitly rather than a row worth quietly deleting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from valuemaxx.core.alias import EntityAlias
from valuemaxx.store.repositories._base import BaseRepository, upsert_stmt
from valuemaxx.store.tables import entity_alias as alias_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from valuemaxx.core.ids import TenantId


class PgEntityAliasRepository(BaseRepository):
    """Async SQLAlchemy persistence for entity aliases."""

    async def append(self, tenant_id: TenantId, alias: EntityAlias, now: datetime) -> None:
        """Record one identity edge; repeating an identical edge is a no-op."""
        (source_type, source_value) = alias.source
        (target_type, target_value) = alias.target
        values = {
            # The id is derived from the edge so an at-least-once sender collides with
            # its own row rather than creating a duplicate the closure would re-walk.
            "id": f"ea_{source_type}:{source_value}>{target_type}:{target_value}",
            "tenant_id": tenant_id,
            "source_type": source_type,
            "source_value": source_value,
            "target_type": target_type,
            "target_value": target_value,
            "created_at": now,
        }
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, alias_table, values, ["tenant_id", "id"]))

    async def list_all(self, tenant_id: TenantId) -> Sequence[EntityAlias]:
        """Every alias in the tenant, for resolving a closure at query time."""
        stmt = require_tenant(select(alias_table), tenant_id, alias_table)
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [
            EntityAlias(
                source=(row["source_type"], row["source_value"]),
                target=(row["target_type"], row["target_value"]),
            )
            for row in rows
        ]


__all__ = ["PgEntityAliasRepository"]
