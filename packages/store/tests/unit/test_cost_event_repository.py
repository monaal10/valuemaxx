"""PgCostEventRepository — idempotent upsert on (tenant, run, attempt) + window scan."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from _store_helpers import make_tenant
from sqlalchemy import func, select
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance
from valuemaxx.core.ids import AttemptId, CostEventId, RunId, TenantId
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.tokens import TokenVector
from valuemaxx.store.repositories.cost_event import PgCostEventRepository
from valuemaxx.store.tables import cost_event as cost_event_table

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _event(
    tenant: TenantId,
    *,
    event_id: str,
    run: str = "run-1",
    attempt: str = "att-1",
    cost: Decimal | None = Decimal("0.0100000000"),
    when: datetime | None = None,
) -> CostEvent:
    return CostEvent(
        tenant_id=tenant,
        id=CostEventId(event_id),
        run_id=RunId(run),
        attempt_id=AttemptId(attempt),
        provider="anthropic",
        model="claude-opus-4",
        tokens=TokenVector(
            input_uncached=10,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=5,
            reasoning=0,
        ),
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=cost,
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=False,
        provenance_warnings=(),
        occurred_at=when or datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )


async def _count_rows(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(select(func.count()).select_from(cost_event_table))
        ).scalar_one()


@pytest.mark.asyncio
async def test_upsert_then_list_for_run(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgCostEventRepository(sessionmaker)
    await repo.upsert(tenant, _event(tenant, event_id="ce-1"))
    found = await repo.list_for_run(tenant, RunId("run-1"))
    assert [e.id for e in found] == [CostEventId("ce-1")]


@pytest.mark.asyncio
async def test_double_upsert_same_idempotency_key_yields_one_row(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """At-least-once ingest: two deliveries of the same (run, attempt) => one row (M7)."""
    tenant = make_tenant()
    repo = PgCostEventRepository(sessionmaker)
    # same (run, attempt) but a different surrogate id and updated cost — the second
    # delivery must update in place, not insert a duplicate.
    await repo.upsert(tenant, _event(tenant, event_id="ce-1", cost=Decimal("0.0100000000")))
    await repo.upsert(tenant, _event(tenant, event_id="ce-1", cost=Decimal("0.0200000000")))
    assert await _count_rows(sessionmaker) == 1
    found = await repo.list_for_run(tenant, RunId("run-1"))
    assert len(found) == 1
    assert found[0].cost_usd == Decimal("0.0200000000")


@pytest.mark.asyncio
async def test_distinct_attempts_are_distinct_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgCostEventRepository(sessionmaker)
    await repo.upsert(tenant, _event(tenant, event_id="ce-1", attempt="att-1"))
    await repo.upsert(tenant, _event(tenant, event_id="ce-2", attempt="att-2"))
    assert await _count_rows(sessionmaker) == 2


@pytest.mark.asyncio
async def test_list_in_window_is_half_open(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgCostEventRepository(sessionmaker)
    await repo.upsert(
        tenant,
        _event(tenant, event_id="ce-1", attempt="a1", when=datetime(2026, 6, 27, 10, tzinfo=UTC)),
    )
    await repo.upsert(
        tenant,
        _event(tenant, event_id="ce-2", attempt="a2", when=datetime(2026, 6, 27, 12, tzinfo=UTC)),
    )
    window = await repo.list_in_window(
        tenant,
        datetime(2026, 6, 27, 10, tzinfo=UTC),
        datetime(2026, 6, 27, 12, tzinfo=UTC),
    )
    assert [e.id for e in window] == [CostEventId("ce-1")]


@pytest.mark.asyncio
async def test_tenant_isolation_on_list(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgCostEventRepository(sessionmaker)
    await repo.upsert(tenant_a, _event(tenant_a, event_id="ce-1"))
    assert await repo.list_for_run(tenant_b, RunId("run-1")) == []
