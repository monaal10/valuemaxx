"""PgAttributionResultRepository — upsert/get per outcome, tenant-scoped."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from valuemaxx.core.attribution import AttributionCandidate, AttributionResult
from valuemaxx.core.enums import BindingTier
from valuemaxx.core.ids import OutcomeEventId, RunId, TenantId
from valuemaxx.store.repositories.attribution import PgAttributionResultRepository

from tests.unit.conftest import make_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _result(tenant: TenantId, *, outcome: str, review: bool = False) -> AttributionResult:
    return AttributionResult(
        tenant_id=tenant,
        outcome_id=OutcomeEventId(outcome),
        run_id=RunId("run-1"),
        tier=BindingTier.DETERMINISTIC,
        bound_by="correlation",
        candidates=(
            AttributionCandidate(
                run_id=RunId("run-1"),
                tier=BindingTier.DETERMINISTIC,
                score=0.9,
                rationale="correlation id match",
            ),
        ),
        review_required=review,
    )


@pytest.mark.asyncio
async def test_upsert_then_get(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    tenant = make_tenant()
    repo = PgAttributionResultRepository(sessionmaker)
    result = _result(tenant, outcome="oe-1")
    await repo.upsert(tenant, result)
    assert await repo.get_for_outcome(tenant, OutcomeEventId("oe-1")) == result


@pytest.mark.asyncio
async def test_upsert_idempotent(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    tenant = make_tenant()
    repo = PgAttributionResultRepository(sessionmaker)
    await repo.upsert(tenant, _result(tenant, outcome="oe-1", review=False))
    await repo.upsert(tenant, _result(tenant, outcome="oe-1", review=True))
    got = await repo.get_for_outcome(tenant, OutcomeEventId("oe-1"))
    assert got is not None
    assert got.review_required is True


@pytest.mark.asyncio
async def test_get_missing_returns_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgAttributionResultRepository(sessionmaker)
    assert await repo.get_for_outcome(tenant, OutcomeEventId("nope")) is None


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgAttributionResultRepository(sessionmaker)
    await repo.upsert(tenant_a, _result(tenant_a, outcome="oe-1"))
    assert await repo.get_for_outcome(tenant_b, OutcomeEventId("oe-1")) is None
