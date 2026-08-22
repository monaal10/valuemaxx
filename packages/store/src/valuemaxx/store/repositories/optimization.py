"""Tenant-scoped persistence for continuous-optimization artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel
from sqlalchemy import delete, select
from valuemaxx.core.optimization import (
    CallSiteBaseline,
    FrontierEntry,
    LinterFinding,
    OptimizationDeployment,
    OptimizationExperiment,
)
from valuemaxx.core.optimization_repositories import (
    BaselineRepository,
    DeploymentRepository,
    ExperimentRepository,
    FindingRepository,
    FrontierRepository,
)
from valuemaxx.store.repositories._base import BaseRepository, as_row, upsert_stmt
from valuemaxx.store.tables import (
    optimization_baseline,
    optimization_deployment,
    optimization_experiment,
    optimization_finding,
    optimization_frontier,
)
from valuemaxx.store.tenant_guard import require_tenant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.base import TenantScopedModel
    from valuemaxx.core.ids import TenantId

_ID_CONFLICT = ("tenant_id", "id")
_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _load(model: type[_ModelT], payload: object) -> _ModelT:
    """Rehydrate JSON-mode storage into a strict pydantic domain model."""
    return model.model_validate(payload, strict=False)


def _require_matching_tenant(tenant_id: TenantId, model: TenantScopedModel) -> None:
    """Reject a model whose embedded tenant disagrees with the repository scope."""
    if model.tenant_id != tenant_id:
        raise ValueError("model tenant_id does not match repository tenant_id")


class PgBaselineRepository(BaseRepository):
    """Async retained baseline history (virtual ``BaselineRepository``)."""

    async def upsert(self, tenant_id: TenantId, baseline: CallSiteBaseline) -> None:
        _require_matching_tenant(tenant_id, baseline)
        values: dict[str, object] = {
            "id": baseline.id,
            "tenant_id": tenant_id,
            "call_site_id": baseline.call_site_id,
            "status": baseline.status.value,
            "activated_at": baseline.activated_at,
            "payload": baseline.model_dump(mode="json"),
        }
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, optimization_baseline, values, _ID_CONFLICT))

    async def list_for_call_site(
        self, tenant_id: TenantId, call_site_id: str
    ) -> Sequence[CallSiteBaseline]:
        stmt = (
            require_tenant(select(optimization_baseline), tenant_id, optimization_baseline)
            .where(optimization_baseline.c.call_site_id == call_site_id)
            .order_by(optimization_baseline.c.activated_at, optimization_baseline.c.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [_load(CallSiteBaseline, as_row(row)["payload"]) for row in rows]


class PgFindingRepository(BaseRepository):
    """Async idempotent structural findings (virtual ``FindingRepository``)."""

    async def upsert(self, tenant_id: TenantId, finding: LinterFinding) -> None:
        _require_matching_tenant(tenant_id, finding)
        values: dict[str, object] = {
            "id": finding.id,
            "tenant_id": tenant_id,
            "call_site_id": finding.call_site_id,
            "kind": finding.kind.value,
            "estimated_savings_usd": finding.estimated_savings_usd,
            "payload": finding.model_dump(mode="json"),
        }
        async with self._sessions.begin() as session:
            await session.execute(upsert_stmt(session, optimization_finding, values, _ID_CONFLICT))

    async def list_for_call_site(
        self, tenant_id: TenantId, call_site_id: str
    ) -> Sequence[LinterFinding]:
        stmt = (
            require_tenant(select(optimization_finding), tenant_id, optimization_finding)
            .where(optimization_finding.c.call_site_id == call_site_id)
            .order_by(optimization_finding.c.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [_load(LinterFinding, as_row(row)["payload"]) for row in rows]


class PgFrontierRepository(BaseRepository):
    """Async replaceable frontier projection (virtual ``FrontierRepository``)."""

    async def replace_for_call_site(
        self,
        tenant_id: TenantId,
        call_site_id: str,
        entries: Sequence[FrontierEntry],
    ) -> None:
        """Atomically replace one call site's ordered frontier."""
        async with self._sessions.begin() as session:
            await session.execute(
                delete(optimization_frontier)
                .where(optimization_frontier.c.tenant_id == tenant_id)
                .where(optimization_frontier.c.call_site_id == call_site_id)
            )
            for ordinal, entry in enumerate(entries):
                await session.execute(
                    optimization_frontier.insert().values(
                        tenant_id=tenant_id,
                        call_site_id=call_site_id,
                        ordinal=ordinal,
                        status=entry.status.value,
                        evidence_tier=int(entry.evidence_tier),
                        cost_per_unit=entry.metrics.cost_per_unit,
                        payload=entry.model_dump(mode="json"),
                    )
                )

    async def list_for_call_site(
        self, tenant_id: TenantId, call_site_id: str
    ) -> Sequence[FrontierEntry]:
        stmt = (
            require_tenant(select(optimization_frontier), tenant_id, optimization_frontier)
            .where(optimization_frontier.c.call_site_id == call_site_id)
            .order_by(optimization_frontier.c.ordinal)
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [_load(FrontierEntry, as_row(row)["payload"]) for row in rows]


class PgExperimentRepository(BaseRepository):
    """Async retained experiment history with exclusive active occupancy."""

    async def upsert(self, tenant_id: TenantId, experiment: OptimizationExperiment) -> None:
        _require_matching_tenant(tenant_id, experiment)
        values: dict[str, object] = {
            "id": experiment.id,
            "tenant_id": tenant_id,
            "call_site_id": experiment.call_site_id,
            "state": experiment.state.value,
            "started_at": experiment.started_at,
            "payload": experiment.model_dump(mode="json"),
        }
        async with self._sessions.begin() as session:
            await session.execute(
                upsert_stmt(session, optimization_experiment, values, _ID_CONFLICT)
            )

    async def list_for_call_site(
        self, tenant_id: TenantId, call_site_id: str
    ) -> Sequence[OptimizationExperiment]:
        stmt = (
            require_tenant(select(optimization_experiment), tenant_id, optimization_experiment)
            .where(optimization_experiment.c.call_site_id == call_site_id)
            .order_by(optimization_experiment.c.started_at, optimization_experiment.c.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [_load(OptimizationExperiment, as_row(row)["payload"]) for row in rows]


class PgDeploymentRepository(BaseRepository):
    """Async separately authorized production deployments."""

    async def upsert(self, tenant_id: TenantId, deployment: OptimizationDeployment) -> None:
        _require_matching_tenant(tenant_id, deployment)
        values: dict[str, object] = {
            "id": deployment.id,
            "tenant_id": tenant_id,
            "call_site_id": deployment.policy.call_site_id,
            "kill_switch_active": deployment.kill_switch_active,
            "authorized_at": deployment.authorized_at,
            "payload": deployment.model_dump(mode="json"),
        }
        async with self._sessions.begin() as session:
            await session.execute(
                upsert_stmt(session, optimization_deployment, values, _ID_CONFLICT)
            )

    async def get_active(
        self, tenant_id: TenantId, call_site_id: str
    ) -> OptimizationDeployment | None:
        stmt = (
            require_tenant(select(optimization_deployment), tenant_id, optimization_deployment)
            .where(optimization_deployment.c.call_site_id == call_site_id)
            .where(optimization_deployment.c.kill_switch_active.is_(False))
            .order_by(
                optimization_deployment.c.authorized_at.desc(),
                optimization_deployment.c.id.desc(),
            )
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(stmt)).mappings().one_or_none()
        if row is None:
            return None
        return _load(OptimizationDeployment, as_row(row)["payload"])


BaselineRepository.register(PgBaselineRepository)
FindingRepository.register(PgFindingRepository)
FrontierRepository.register(PgFrontierRepository)
ExperimentRepository.register(PgExperimentRepository)
DeploymentRepository.register(PgDeploymentRepository)

__all__ = [
    "PgBaselineRepository",
    "PgDeploymentRepository",
    "PgExperimentRepository",
    "PgFindingRepository",
    "PgFrontierRepository",
]
