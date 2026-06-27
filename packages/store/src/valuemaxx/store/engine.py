"""The storage port — async engine + sessionmaker construction (§9).

Storage is configurable behind a port: the production store is Postgres (asyncpg
driver), and a SQLite/aiosqlite URL is accepted for the driver-agnostic unit path.
Both return a :class:`~sqlalchemy.ext.asyncio.AsyncEngine`, so every repository is
written once against the async session API and never against a concrete driver.

A repository takes an ``async_sessionmaker`` (not a bare engine) so it owns the
unit-of-work boundary per call — one transaction per repository operation — which
keeps tenant isolation and idempotent upserts atomic.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an async engine for a storage URL (Postgres in prod, SQLite for unit).

    Args:
        url: a SQLAlchemy async URL, e.g. ``postgresql+asyncpg://...`` or
            ``sqlite+aiosqlite://``.
        echo: when True, log every emitted statement (debugging only).

    Returns:
        An :class:`~sqlalchemy.ext.asyncio.AsyncEngine` bound to the URL.
    """
    return create_async_engine(url, echo=echo, future=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build an ``async_sessionmaker`` over an engine (the repository constructor arg).

    ``expire_on_commit=False`` keeps returned attribute values readable after the
    unit of work commits, so a mapper can build a domain object from a just-written
    row without a second round-trip.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


__all__ = ["create_engine", "create_sessionmaker"]
