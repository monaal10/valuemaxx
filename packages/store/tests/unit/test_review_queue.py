"""PgReviewQueue — enqueue candidate/likely bindings, list pending, tenant-scoped."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from _store_helpers import make_tenant
from valuemaxx.store.repositories.review_queue import PgReviewQueue

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class _FixedClock:
    """A deterministic clock so enqueue ordering is reproducible in tests."""

    def __init__(self) -> None:
        self._n = 0

    def now(self) -> datetime:
        self._n += 1
        return datetime(2026, 6, 27, 12, 0, self._n, tzinfo=UTC)


@pytest.mark.asyncio
async def test_enqueue_then_list_pending(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgReviewQueue(sessionmaker, now=_FixedClock().now)
    item = {"binding": "candidate", "outcome_id": "oe-1", "run_id": "run-1"}
    await repo.enqueue(tenant, item)
    pending = await repo.list_pending(tenant)
    assert list(pending) == [item]


@pytest.mark.asyncio
async def test_pending_preserves_enqueue_order(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgReviewQueue(sessionmaker, now=_FixedClock().now)
    await repo.enqueue(tenant, {"n": 1})
    await repo.enqueue(tenant, {"n": 2})
    pending = await repo.list_pending(tenant)
    assert [p["n"] for p in pending] == [1, 2]  # type: ignore[index]  # known dict shape in test


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgReviewQueue(sessionmaker, now=_FixedClock().now)
    await repo.enqueue(tenant_a, {"a": 1})
    assert await repo.list_pending(tenant_b) == []
