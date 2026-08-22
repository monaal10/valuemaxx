"""Continuous-optimization repository behavior and tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from _store_helpers import make_tenant
from sqlalchemy.exc import IntegrityError
from valuemaxx.core.optimization import (
    ApplicationMode,
    ApplicationPolicy,
    BaselineCause,
    BaselineStatus,
    CallSiteBaseline,
    CandidateMetrics,
    CandidateStatus,
    EvidenceTier,
    ExperimentState,
    FrontierEntry,
    LinterFinding,
    LinterFindingKind,
    OptimizationConfig,
    OptimizationDeployment,
    OptimizationExperiment,
)
from valuemaxx.store.repositories.optimization import (
    PgBaselineRepository,
    PgDeploymentRepository,
    PgExperimentRepository,
    PgFindingRepository,
    PgFrontierRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from valuemaxx.core.ids import TenantId

_AT = datetime(2026, 8, 22, 12, tzinfo=UTC)


def _config(model: str = "claude-haiku") -> OptimizationConfig:
    return OptimizationConfig(model=model, provider="anthropic", max_tokens=512)


def _baseline(tenant: TenantId, baseline_id: str, call_site: str) -> CallSiteBaseline:
    return CallSiteBaseline(
        tenant_id=tenant,
        id=baseline_id,
        call_site_id=call_site,
        config_identity="a" * 64,
        status=BaselineStatus.ACTIVE,
        dominant_share=Decimal("0.80"),
        outcome_rate=Decimal("0.08"),
        cause=BaselineCause.CUSTOMER_CHANGE,
        activated_at=_AT,
    )


def _finding(tenant: TenantId, finding_id: str, call_site: str) -> LinterFinding:
    return LinterFinding(
        tenant_id=tenant,
        id=finding_id,
        call_site_id=call_site,
        kind=LinterFindingKind.CACHE_MISALIGNMENT,
        summary="stable prefix follows volatile text",
        evidence="3800 stable tokens across 50 calls",
        evidence_tier=EvidenceTier.STATIC,
        estimated_savings_usd=Decimal("12.34"),
    )


def _frontier(model: str, status: CandidateStatus = CandidateStatus.PASSED) -> FrontierEntry:
    return FrontierEntry(
        config=_config(model),
        metrics=CandidateMetrics(
            cost_per_unit=Decimal("0.07"),
            outcome_rate=Decimal("0.081"),
            error_rate=Decimal("0.01"),
            refusal_rate=Decimal("0.02"),
            p95_latency_ms=800,
            sample_size=9400,
        ),
        evidence_tier=EvidenceTier.LIVE_GUARDRAILS,
        status=status,
    )


def _experiment(
    tenant: TenantId,
    experiment_id: str,
    call_site: str,
    state: ExperimentState,
) -> OptimizationExperiment:
    return OptimizationExperiment(
        tenant_id=tenant,
        id=experiment_id,
        call_site_id=call_site,
        baseline_id="base-1",
        candidate=_config(),
        state=state,
        ramp_percentage=1,
        started_at=_AT,
    )


def _deployment(
    tenant: TenantId, deployment_id: str, call_site: str, *, killed: bool = False
) -> OptimizationDeployment:
    return OptimizationDeployment(
        tenant_id=tenant,
        id=deployment_id,
        policy=ApplicationPolicy(
            tenant_id=tenant,
            call_site_id=call_site,
            mode=ApplicationMode.APPROVE,
            enabled=True,
        ),
        source_config_identity="b" * 64,
        target_config=_config(),
        authorized_by="operator@example.com",
        authorized_at=_AT,
        kill_switch_active=killed,
    )


@pytest.mark.asyncio
async def test_baseline_upsert_retains_history_and_scopes_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, other = make_tenant(), make_tenant()
    repo = PgBaselineRepository(sessionmaker)
    await repo.upsert(tenant, _baseline(tenant, "base-1", "site-a"))
    await repo.upsert(tenant, _baseline(tenant, "base-2", "site-a"))
    assert [b.id for b in await repo.list_for_call_site(tenant, "site-a")] == [
        "base-1",
        "base-2",
    ]
    assert await repo.list_for_call_site(other, "site-a") == []


@pytest.mark.asyncio
async def test_repository_rejects_model_from_another_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, other = make_tenant(), make_tenant()
    repo = PgBaselineRepository(sessionmaker)
    with pytest.raises(ValueError, match="tenant_id does not match"):
        await repo.upsert(tenant, _baseline(other, "base-1", "site-a"))


@pytest.mark.asyncio
async def test_finding_upsert_is_idempotent_and_filtered_by_call_site(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgFindingRepository(sessionmaker)
    finding = _finding(tenant, "finding-1", "site-a")
    await repo.upsert(tenant, finding)
    await repo.upsert(tenant, finding)
    await repo.upsert(tenant, _finding(tenant, "finding-2", "site-b"))
    assert list(await repo.list_for_call_site(tenant, "site-a")) == [finding]


@pytest.mark.asyncio
async def test_frontier_replace_is_atomic_projection_replacement(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgFrontierRepository(sessionmaker)
    await repo.replace_for_call_site(tenant, "site-a", [_frontier("model-a"), _frontier("model-b")])
    await repo.replace_for_call_site(tenant, "site-a", [_frontier("model-c")])
    assert list(await repo.list_for_call_site(tenant, "site-a")) == [_frontier("model-c")]


@pytest.mark.asyncio
async def test_one_active_experiment_per_call_site(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgExperimentRepository(sessionmaker)
    await repo.upsert(tenant, _experiment(tenant, "exp-1", "site-a", ExperimentState.RUNNING))
    with pytest.raises(IntegrityError):
        await repo.upsert(tenant, _experiment(tenant, "exp-2", "site-a", ExperimentState.PENDING))


@pytest.mark.asyncio
async def test_terminal_experiment_releases_call_site(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant = make_tenant()
    repo = PgExperimentRepository(sessionmaker)
    await repo.upsert(tenant, _experiment(tenant, "exp-1", "site-a", ExperimentState.RUNNING))
    await repo.upsert(tenant, _experiment(tenant, "exp-1", "site-a", ExperimentState.COMPLETED))
    await repo.upsert(tenant, _experiment(tenant, "exp-2", "site-a", ExperimentState.RUNNING))
    assert len(await repo.list_for_call_site(tenant, "site-a")) == 2


@pytest.mark.asyncio
async def test_deployment_get_active_ignores_killed_and_other_tenants(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    tenant, other = make_tenant(), make_tenant()
    repo = PgDeploymentRepository(sessionmaker)
    active = _deployment(tenant, "deploy-1", "site-a")
    await repo.upsert(tenant, active)
    await repo.upsert(tenant, _deployment(tenant, "deploy-2", "site-b", killed=True))
    assert await repo.get_active(tenant, "site-a") == active
    assert await repo.get_active(tenant, "site-b") is None
    assert await repo.get_active(other, "site-a") is None
