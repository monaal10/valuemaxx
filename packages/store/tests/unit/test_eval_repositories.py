"""PgEvalDatasetRepository + PgEvalRecommendationRepository — JSON artifact round-trips."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from valuemaxx.core.enums import EvalGrade, LabelSource
from valuemaxx.core.eval import EvalCase, EvalDataset, EvalRecommendation
from valuemaxx.store.repositories.eval_dataset import PgEvalDatasetRepository
from valuemaxx.store.repositories.eval_recommendation import PgEvalRecommendationRepository

from tests.unit.conftest import make_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from valuemaxx.core.ids import TenantId


def _dataset(tenant: TenantId, *, dataset_id: str, version: int) -> EvalDataset:
    return EvalDataset(
        tenant_id=tenant,
        id=dataset_id,
        name="support-traces",
        version=version,
        cases=(
            EvalCase(
                id="case-1",
                inputs={"q": "where is my order", "nested": {"k": [1, 2]}},
                label_source=LabelSource.HUMAN_LABELED,
                source_trace_id="trace-1",
            ),
        ),
    )


def _recommendation(tenant: TenantId, *, incumbent: str, grade: EvalGrade) -> EvalRecommendation:
    label = (
        LabelSource.HUMAN_LABELED if grade is EvalGrade.RELIABLE else LabelSource.LLM_JUDGE
    )
    return EvalRecommendation(
        tenant_id=tenant,
        recommended_model="claude-haiku-4",
        incumbent_model=incumbent,
        grade=grade,
        label_source=label,
        parity_ci95=(Decimal("0.01"), Decimal("0.05")),
        latency_p50_ms=120.0,
        latency_p95_ms=300.0,
        latency_p99_ms=450.0,
        sample_disagreements=({"case": "case-1"},),
        gap_distribution={"minor": 3},
        pareto_frontier=({"model": "claude-haiku-4", "cost": 0.1},),
        methodology="two-phase gate",
    )


@pytest.mark.asyncio
async def test_dataset_upsert_then_get(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgEvalDatasetRepository(sessionmaker)
    dataset = _dataset(tenant, dataset_id="ds-1", version=1)
    await repo.upsert(tenant, dataset)
    assert await repo.get(tenant, "ds-1") == dataset


@pytest.mark.asyncio
async def test_dataset_get_returns_latest_version(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgEvalDatasetRepository(sessionmaker)
    await repo.upsert(tenant, _dataset(tenant, dataset_id="ds-1", version=1))
    await repo.upsert(tenant, _dataset(tenant, dataset_id="ds-1", version=2))
    got = await repo.get(tenant, "ds-1")
    assert got is not None
    assert got.version == 2


@pytest.mark.asyncio
async def test_dataset_get_missing_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgEvalDatasetRepository(sessionmaker)
    assert await repo.get(tenant, "nope") is None


@pytest.mark.asyncio
async def test_dataset_tenant_isolation(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgEvalDatasetRepository(sessionmaker)
    await repo.upsert(tenant_a, _dataset(tenant_a, dataset_id="ds-1", version=1))
    assert await repo.get(tenant_b, "ds-1") is None


@pytest.mark.asyncio
async def test_recommendation_upsert_then_list(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgEvalRecommendationRepository(sessionmaker)
    rec = _recommendation(tenant, incumbent="claude-opus-4", grade=EvalGrade.RELIABLE)
    await repo.upsert(tenant, rec)
    found = await repo.list_for_incumbent(tenant, "claude-opus-4")
    assert list(found) == [rec]


@pytest.mark.asyncio
async def test_recommendation_list_filters_incumbent(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgEvalRecommendationRepository(sessionmaker)
    await repo.upsert(
        tenant, _recommendation(tenant, incumbent="claude-opus-4", grade=EvalGrade.DIRECTIONAL)
    )
    await repo.upsert(
        tenant, _recommendation(tenant, incumbent="gpt-5", grade=EvalGrade.DIRECTIONAL)
    )
    found = await repo.list_for_incumbent(tenant, "claude-opus-4")
    assert all(r.incumbent_model == "claude-opus-4" for r in found)
    assert len(found) == 1


@pytest.mark.asyncio
async def test_recommendation_tenant_isolation(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    repo = PgEvalRecommendationRepository(sessionmaker)
    await repo.upsert(
        tenant_a, _recommendation(tenant_a, incumbent="claude-opus-4", grade=EvalGrade.DIRECTIONAL)
    )
    assert await repo.list_for_incumbent(tenant_b, "claude-opus-4") == []
