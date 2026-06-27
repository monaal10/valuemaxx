"""PgRunRepository — tenant-scoped CRUD with idempotent upsert and entity lookup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from _store_helpers import make_tenant
from valuemaxx.core.ids import RunId, TenantId
from valuemaxx.core.run import Run
from valuemaxx.store.repositories.run import PgRunRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _run(tenant: TenantId, run_id: str, *, agent: str | None = "bot") -> Run:
    return Run(
        tenant_id=tenant,
        id=RunId(run_id),
        agent_name=agent,
        started_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
        ended_at=None,
        entity_keys=frozenset({("ticket", run_id)}),
    )


@pytest.mark.asyncio
async def test_upsert_then_get_roundtrips(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgRunRepository(sessionmaker)
    run = _run(tenant, "run-1")
    await repo.upsert(tenant, run)
    assert await repo.get(tenant, RunId("run-1")) == run


@pytest.mark.asyncio
async def test_get_missing_returns_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgRunRepository(sessionmaker)
    assert await repo.get(tenant, RunId("nope")) is None


@pytest.mark.asyncio
async def test_upsert_is_idempotent_on_id(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgRunRepository(sessionmaker)
    await repo.upsert(tenant, _run(tenant, "run-1", agent="first"))
    await repo.upsert(tenant, _run(tenant, "run-1", agent="second"))
    got = await repo.get(tenant, RunId("run-1"))
    assert got is not None
    assert got.agent_name == "second"


@pytest.mark.asyncio
async def test_list_by_entity_scopes_to_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgRunRepository(sessionmaker)
    await repo.upsert(tenant_a, _run(tenant_a, "run-a"))
    await repo.upsert(tenant_b, _run(tenant_b, "run-a"))
    found = await repo.list_by_entity(tenant_a, ("ticket", "run-a"))
    assert [r.id for r in found] == [RunId("run-a")]
    assert all(r.tenant_id == tenant_a for r in found)


@pytest.mark.asyncio
async def test_tenant_a_cannot_read_tenant_b_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgRunRepository(sessionmaker)
    await repo.upsert(tenant_a, _run(tenant_a, "run-1"))
    assert await repo.get(tenant_b, RunId("run-1")) is None
