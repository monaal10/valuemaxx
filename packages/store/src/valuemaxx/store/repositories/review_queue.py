"""PgReviewQueue — the queue for candidate/likely bindings (advisory, §4).

Fulfils :class:`~valuemaxx.core.repositories.ReviewQueue` (virtual subclass). Candidate
and likely bindings are advisory and never billing-grade; they land here for human
review. ``enqueue`` stores the item as JSON with an enqueue timestamp; ``list_pending``
returns the items in enqueue order. The clock and id generator are injected (never a
bare ``datetime.now`` / ``uuid4`` in app code, per AGENTS §1) so ordering is reproducible.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import select
from valuemaxx.core.repositories import ReviewQueue
from valuemaxx.store.repositories._base import BaseRepository, as_row
from valuemaxx.store.tables import review_queue as queue_table
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from valuemaxx.core.ids import TenantId


def _utc_now() -> datetime:
    """The default clock — tz-aware UTC now (overridable for deterministic tests)."""
    return datetime.now(UTC)


def _new_uuid() -> str:
    """The default id generator — a fresh uuid4 hex (overridable for tests)."""
    return uuid4().hex


def _as_jsonable(item: object) -> object:
    """Render a review item into something the ``jsonb`` column can store.

    A pydantic model is dumped in JSON mode (so nested datetimes/UUIDs/Decimals become
    JSON scalars, not Python objects the encoder would choke on). Anything already
    JSON-shaped passes through untouched.
    """
    if isinstance(item, BaseModel):
        return item.model_dump(mode="json")
    return item


class PgReviewQueue(BaseRepository):
    """Async persistence for the review queue (virtual ``ReviewQueue``)."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        now: Callable[[], datetime] = _utc_now,
        new_id: Callable[[], str] = _new_uuid,
    ) -> None:
        """Construct over a sessionmaker, with injectable clock + id generator.

        Args:
            sessions: the ``async_sessionmaker`` for the unit of work.
            now: returns the current tz-aware time (injected for determinism).
            new_id: returns a fresh unique row id (injected for determinism).
        """
        super().__init__(sessions)
        self._now = now
        self._new_id = new_id

    async def enqueue(self, tenant_id: TenantId, item: object) -> None:
        """Enqueue a review item (a candidate/likely binding awaiting human review).

        The ``ReviewQueue`` ABC types ``item`` as ``object`` because the queue is
        deliberately shape-agnostic, but the column is ``jsonb`` — so what actually
        arrives (an :class:`~valuemaxx.core.AttributionResult` from the cascade) must
        be serialized here rather than handed to the driver raw. Passing the model
        straight through raised ``TypeError: Object of type AttributionResult is not
        JSON serializable`` from the JSON encoder, which surfaced as a 500 on
        ``bind_outcome`` for every advisory (candidate/likely) binding — i.e. exactly
        the bindings the review queue exists to hold.
        """
        values: dict[str, object] = {
            "id": self._new_id(),
            "tenant_id": tenant_id,
            "item": _as_jsonable(item),
            "enqueued_at": self._now(),
        }
        async with self._sessions.begin() as session:
            await session.execute(queue_table.insert().values(**values))

    async def list_pending(self, tenant_id: TenantId) -> Sequence[object]:
        """List the pending review items for the tenant, in enqueue order."""
        stmt = require_tenant(select(queue_table.c.item), tenant_id, queue_table).order_by(
            queue_table.c.enqueued_at, queue_table.c.id
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [as_row(row)["item"] for row in rows]


ReviewQueue.register(PgReviewQueue)

__all__ = ["PgReviewQueue"]
