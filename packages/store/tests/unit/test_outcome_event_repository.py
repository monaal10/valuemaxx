"""PgOutcomeEventRepository — correlation upsert, retract (confirmed->retracted), unbound."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from valuemaxx.core.enums import BindingTier, SignalClass
from valuemaxx.core.ids import CorrelationId, OutcomeEventId, RunId, TenantId
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.store.repositories.outcome_event import PgOutcomeEventRepository
from valuemaxx.store.tables import outcome_event as outcome_event_table

from tests.unit.conftest import make_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _outcome(
    tenant: TenantId,
    *,
    outcome_id: str,
    signal: SignalClass = SignalClass.OUTCOME_CONFIRMED,
    correlation: str | None = None,
    bound: bool = False,
) -> OutcomeEvent:
    binding = (
        OutcomeBinding(run_id=RunId("run-1"), tier=BindingTier.EXACT, bound_by="correlation")
        if bound
        else OutcomeBinding(run_id=None, tier=None, bound_by=None)
    )
    return OutcomeEvent(
        tenant_id=tenant,
        id=OutcomeEventId(outcome_id),
        name="loan_funded",
        signal_class=signal,
        value=Decimal("100.0000000000"),
        occurred_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
        binding=binding,
        entity_keys=frozenset({("application", outcome_id)}),
        correlation_id=CorrelationId(correlation) if correlation is not None else None,
        source="webhook",
        raw={"amount": 100},
    )


async def _count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(select(func.count()).select_from(outcome_event_table))
        ).scalar_one()


@pytest.mark.asyncio
async def test_upsert_then_get(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    tenant = make_tenant()
    repo = PgOutcomeEventRepository(sessionmaker)
    outcome = _outcome(tenant, outcome_id="oe-1", correlation="corr-1")
    await repo.upsert(tenant, outcome)
    assert await repo.get(tenant, OutcomeEventId("oe-1")) == outcome


@pytest.mark.asyncio
async def test_upsert_idempotent_on_id(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    tenant = make_tenant()
    repo = PgOutcomeEventRepository(sessionmaker)
    await repo.upsert(tenant, _outcome(tenant, outcome_id="oe-1", correlation="corr-1"))
    await repo.upsert(tenant, _outcome(tenant, outcome_id="oe-1", correlation="corr-1"))
    assert await _count(sessionmaker) == 1


@pytest.mark.asyncio
async def test_retract_confirmed_flips_to_retracted(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgOutcomeEventRepository(sessionmaker)
    await repo.upsert(
        tenant, _outcome(tenant, outcome_id="oe-1", signal=SignalClass.OUTCOME_CONFIRMED)
    )
    await repo.retract(tenant, OutcomeEventId("oe-1"))
    got = await repo.get(tenant, OutcomeEventId("oe-1"))
    assert got is not None
    assert got.signal_class is SignalClass.OUTCOME_RETRACTED


@pytest.mark.asyncio
async def test_retract_non_confirmed_raises(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgOutcomeEventRepository(sessionmaker)
    await repo.upsert(
        tenant, _outcome(tenant, outcome_id="oe-1", signal=SignalClass.ACTION_ATTEMPTED)
    )
    with pytest.raises(ValueError, match="confirmed"):
        await repo.retract(tenant, OutcomeEventId("oe-1"))


@pytest.mark.asyncio
async def test_retract_missing_raises(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    tenant = make_tenant()
    repo = PgOutcomeEventRepository(sessionmaker)
    with pytest.raises(ValueError, match="not found"):
        await repo.retract(tenant, OutcomeEventId("nope"))


@pytest.mark.asyncio
async def test_list_unbound_returns_only_unbound(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgOutcomeEventRepository(sessionmaker)
    await repo.upsert(tenant, _outcome(tenant, outcome_id="oe-1", correlation="c1", bound=False))
    await repo.upsert(tenant, _outcome(tenant, outcome_id="oe-2", correlation="c2", bound=True))
    unbound = await repo.list_unbound(tenant)
    assert [o.id for o in unbound] == [OutcomeEventId("oe-1")]


@pytest.mark.asyncio
async def test_tenant_isolation_on_get(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgOutcomeEventRepository(sessionmaker)
    await repo.upsert(tenant_a, _outcome(tenant_a, outcome_id="oe-1", correlation="c1"))
    assert await repo.get(tenant_b, OutcomeEventId("oe-1")) is None
