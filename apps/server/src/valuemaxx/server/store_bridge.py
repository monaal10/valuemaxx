"""Sync->async store bridge — drive the async store from sync capability handlers.

The store repositories are async SQLAlchemy; capability handlers (and the FastAPI
projection that calls them) invoke their handler **synchronously**. This bridge
closes that gap without leaking async into the framework-free logic packages: a
:class:`~anyio.from_thread.BlockingPortal` runs a dedicated event loop in its own
thread, the async engine + sessionmaker + concrete repositories are built **on that
loop**, and every sync repository call is forwarded into the portal and blocks the
caller until the coroutine completes.

Keeping the engine and all its calls on one loop is mandatory: an ``aiosqlite`` /
``asyncpg`` connection is bound to the loop that created it, so the portal owns the
engine's entire lifecycle. The sync wrappers (:class:`SyncCostEventRepository`) are
real :class:`~valuemaxx.core.repositories.CostEventRepository` subclasses, so they
satisfy the synchronous core ABC the capture/metrics runtimes expect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from anyio.from_thread import BlockingPortal, start_blocking_portal
from typing_extensions import override
from valuemaxx.core.repositories import CostEventRepository, OutcomeEventRepository
from valuemaxx.store.engine import create_engine, create_sessionmaker
from valuemaxx.store.migrations_api import upgrade_to_head
from valuemaxx.store.repositories import PgCostEventRepository, PgOutcomeEventRepository

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AbstractContextManager
    from datetime import datetime
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
    from valuemaxx.core.cost import CostEvent
    from valuemaxx.core.ids import OutcomeEventId, RunId, TenantId
    from valuemaxx.core.outcome import OutcomeEvent


class StoreBridge:
    """Owns a blocking portal + the async store, exposing sync repositories.

    Build with :meth:`open`; the engine, sessionmaker, and concrete async
    repositories are created on the portal's event loop. Migrations run first
    (synchronously, via the sync alembic runner) so the schema exists before any
    async repository call. Always :meth:`close` (or use as a context manager) to
    dispose the engine on its own loop and stop the portal.
    """

    def __init__(
        self,
        portal_cm: AbstractContextManager[BlockingPortal],
        portal: BlockingPortal,
        engine: AsyncEngine,
        sessions: async_sessionmaker[AsyncSession],
    ) -> None:
        self._portal_cm = portal_cm
        self._portal = portal
        self._engine = engine
        self._sessions = sessions
        self._cost_events = PgCostEventRepository(sessions)
        self._outcome_events = PgOutcomeEventRepository(sessions)

    @classmethod
    def open(cls, database_url: str, *, run_migrations: bool = True) -> StoreBridge:
        """Open a bridge over ``database_url``: run migrations, build the async store.

        Migrations apply on the (synchronous) alembic runner before the async engine
        is built, so the schema is present for the first repository call. The portal
        is started and the engine/sessionmaker are constructed on its loop.
        """
        if run_migrations:
            upgrade_to_head(database_url)
        portal_cm = start_blocking_portal()
        portal = portal_cm.__enter__()
        try:
            engine = portal.call(_build_engine, database_url)
        except BaseException:
            portal_cm.__exit__(None, None, None)
            raise
        sessions = create_sessionmaker(engine)
        return cls(portal_cm, portal, engine, sessions)

    @property
    def cost_events(self) -> SyncCostEventRepository:
        """A synchronous :class:`~valuemaxx.core.repositories.CostEventRepository`."""
        return SyncCostEventRepository(self._portal, self._cost_events)

    @property
    def outcome_events(self) -> SyncOutcomeEventRepository:
        """A synchronous :class:`~valuemaxx.core.repositories.OutcomeEventRepository`."""
        return SyncOutcomeEventRepository(self._portal, self._outcome_events)

    def close(self) -> None:
        """Dispose the engine on the portal's loop, then stop the portal."""
        try:
            self._portal.call(self._engine.dispose)
        finally:
            self._portal_cm.__exit__(None, None, None)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


async def _build_engine(database_url: str) -> AsyncEngine:
    """Create the async engine on the portal's event loop (connections bind to it)."""
    return create_engine(database_url)


class SyncCostEventRepository(CostEventRepository):
    """Sync facade over the async :class:`PgCostEventRepository`, via the portal.

    Every method forwards the corresponding async repository coroutine into the
    portal and blocks until it completes, so this satisfies the synchronous core
    :class:`~valuemaxx.core.repositories.CostEventRepository` ABC that the
    capture/metrics runtimes are typed against.
    """

    def __init__(self, portal: BlockingPortal, repo: PgCostEventRepository) -> None:
        self._portal = portal
        self._repo = repo

    @override
    def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        self._portal.call(self._repo.upsert, tenant_id, event)

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        return self._portal.call(self._repo.list_for_run, tenant_id, run_id)

    @override
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        return self._portal.call(self._repo.list_in_window, tenant_id, start, end)


class SyncOutcomeEventRepository(OutcomeEventRepository):
    """Sync facade over the async :class:`PgOutcomeEventRepository`, via the portal."""

    def __init__(self, portal: BlockingPortal, repo: PgOutcomeEventRepository) -> None:
        self._portal = portal
        self._repo = repo

    @override
    def upsert(self, tenant_id: TenantId, event: OutcomeEvent) -> None:
        self._portal.call(self._repo.upsert, tenant_id, event)

    @override
    def get(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> OutcomeEvent | None:
        return self._portal.call(self._repo.get, tenant_id, outcome_id)

    @override
    def retract(self, tenant_id: TenantId, outcome_id: OutcomeEventId) -> None:
        self._portal.call(self._repo.retract, tenant_id, outcome_id)

    @override
    def list_unbound(self, tenant_id: TenantId) -> Sequence[OutcomeEvent]:
        return self._portal.call(self._repo.list_unbound, tenant_id)


__all__ = ["StoreBridge", "SyncCostEventRepository", "SyncOutcomeEventRepository"]
