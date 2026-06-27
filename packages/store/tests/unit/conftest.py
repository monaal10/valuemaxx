"""Unit-test fixtures — an in-process async SQLite store with the real schema.

These fixtures give the repository unit tests a *real* async SQLAlchemy session
(not a mock) backed by file-based SQLite, with the production schema applied from
the shared MetaData. SQLite exercises the same repository code paths the Postgres
integration suite does; the JSONB byte-fidelity and migration-drift checks that
genuinely need Postgres live in ``tests/integration`` (real testcontainer).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest_asyncio
from valuemaxx.core.ids import TenantId
from valuemaxx.store.engine import create_engine, create_sessionmaker
from valuemaxx.store.tables import metadata

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest_asyncio.fixture
async def sessionmaker(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A sessionmaker over a fresh file-based async SQLite db with the schema created."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'store.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    try:
        yield create_sessionmaker(engine)
    finally:
        await engine.dispose()


def make_tenant() -> TenantId:
    """A fresh random tenant id for isolation tests."""
    return TenantId(uuid4())
