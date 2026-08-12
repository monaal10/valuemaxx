"""PgEntityAliasRepository — tenant-scoped, idempotent identity edges."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from _store_helpers import make_tenant
from valuemaxx.core.alias import EntityAlias
from valuemaxx.store.repositories.entity_alias import PgEntityAliasRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
_ALIAS = EntityAlias(source=("session_id", "abc"), target=("lead_id", "8172"))


@pytest.mark.asyncio
async def test_append_then_list_roundtrips(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgEntityAliasRepository(sessionmaker)

    await repo.append(tenant, _ALIAS, _NOW)

    assert list(await repo.list_all(tenant)) == [_ALIAS]


@pytest.mark.asyncio
async def test_repeating_an_edge_does_not_duplicate_it(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """An at-least-once sender must not multiply the edges the closure walks.

    A duplicated edge changes nothing about what is true, but it does make the same
    identity claim count twice in any audit of how a join was reached.
    """
    tenant = make_tenant()
    repo = PgEntityAliasRepository(sessionmaker)

    await repo.append(tenant, _ALIAS, _NOW)
    await repo.append(tenant, _ALIAS, _NOW)

    assert len(await repo.list_all(tenant)) == 1


@pytest.mark.asyncio
async def test_one_tenants_aliases_are_invisible_to_another(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Leaking an alias across tenants would merge two customers' entities."""
    tenant, other = make_tenant(), make_tenant()
    repo = PgEntityAliasRepository(sessionmaker)

    await repo.append(tenant, _ALIAS, _NOW)

    assert list(await repo.list_all(other)) == []
