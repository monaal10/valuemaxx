"""PgRawRecordRepository — JSONB payload round-trip + GDPR erase-by-entity (H10)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from valuemaxx.store.repositories.raw_record import PgRawRecordRepository

from tests.unit.conftest import make_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_NESTED = {
    "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
    "usage": {"input_tokens": 10, "output_tokens": 5},
    "meta": {"nested": {"deep": [1, 2, {"k": "v"}]}},
}


@pytest.mark.asyncio
async def test_put_then_get_roundtrips_nested_payload(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgRawRecordRepository(sessionmaker)
    await repo.put(tenant, "rec-1", _NESTED, frozenset({("ticket", "T-1")}))
    assert await repo.get(tenant, "rec-1") == _NESTED


@pytest.mark.asyncio
async def test_get_missing_returns_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgRawRecordRepository(sessionmaker)
    assert await repo.get(tenant, "nope") is None


@pytest.mark.asyncio
async def test_put_overwrites_same_id(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgRawRecordRepository(sessionmaker)
    await repo.put(tenant, "rec-1", {"v": 1}, frozenset())
    await repo.put(tenant, "rec-1", {"v": 2}, frozenset())
    assert await repo.get(tenant, "rec-1") == {"v": 2}


@pytest.mark.asyncio
async def test_erase_by_entity_deletes_matching_and_counts(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgRawRecordRepository(sessionmaker)
    await repo.put(tenant, "rec-1", {"a": 1}, frozenset({("ticket", "T-1")}))
    await repo.put(tenant, "rec-2", {"b": 2}, frozenset({("ticket", "T-1"), ("user", "U-9")}))
    await repo.put(tenant, "rec-3", {"c": 3}, frozenset({("ticket", "T-2")}))
    erased = await repo.erase_by_entity(tenant, ("ticket", "T-1"))
    assert erased == 2
    assert await repo.get(tenant, "rec-1") is None
    assert await repo.get(tenant, "rec-2") is None
    assert await repo.get(tenant, "rec-3") == {"c": 3}


@pytest.mark.asyncio
async def test_erase_scoped_to_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgRawRecordRepository(sessionmaker)
    await repo.put(tenant_a, "rec-1", {"a": 1}, frozenset({("ticket", "T-1")}))
    await repo.put(tenant_b, "rec-1", {"b": 2}, frozenset({("ticket", "T-1")}))
    erased = await repo.erase_by_entity(tenant_a, ("ticket", "T-1"))
    assert erased == 1
    assert await repo.get(tenant_b, "rec-1") == {"b": 2}


@pytest.mark.asyncio
async def test_tenant_isolation_on_get(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgRawRecordRepository(sessionmaker)
    await repo.put(tenant_a, "rec-1", {"a": 1}, frozenset())
    assert await repo.get(tenant_b, "rec-1") is None
