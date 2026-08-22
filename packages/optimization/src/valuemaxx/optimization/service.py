"""Store-agnostic orchestration for optimization operations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.optimization.frontier import build_frontier
from valuemaxx.optimization.linter import lint_traffic
from valuemaxx.optimization.search import prefilter_by_cost, successive_halving

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from valuemaxx.core import TenantId
    from valuemaxx.core.optimization import (
        ApplicationPolicy,
        CandidateMetrics,
        FrontierEntry,
        LinterFinding,
        OptimizationConfig,
        OptimizationConstraints,
        OptimizationDeployment,
    )
    from valuemaxx.core.optimization_repositories import (
        DeploymentRepository,
        FindingRepository,
        FrontierRepository,
    )
    from valuemaxx.optimization.frontier import FrontierCandidate
    from valuemaxx.optimization.linter import TrafficCall
    from valuemaxx.optimization.search import HalvingResult, SearchCandidate, StageEvaluator


@dataclass(slots=True)
class OptimizationService:
    """Coordinates pure algorithms through tenant-scoped repository ports."""

    findings: FindingRepository
    frontiers: FrontierRepository
    deployments: DeploymentRepository

    def lint_call_site(
        self, *, tenant_id: TenantId, call_site_id: str, calls: Sequence[TrafficCall]
    ) -> tuple[LinterFinding, ...]:
        found = lint_traffic(tenant_id=tenant_id, call_site_id=call_site_id, calls=calls)
        for finding in found:
            self.findings.upsert(tenant_id, finding)
        return found

    def search(
        self,
        *,
        incumbent_cost: Decimal,
        candidates: Sequence[SearchCandidate],
        evaluate: StageEvaluator,
        minimum_savings: Decimal = Decimal("0.05"),
    ) -> HalvingResult:
        eligible = prefilter_by_cost(
            incumbent_cost=incumbent_cost,
            candidates=candidates,
            minimum_savings=minimum_savings,
        )
        return successive_halving(eligible, evaluate=evaluate)

    def evaluate_frontier(
        self,
        *,
        tenant_id: TenantId,
        call_site_id: str,
        baseline: CandidateMetrics,
        constraints: OptimizationConstraints,
        candidates: Sequence[FrontierCandidate],
    ) -> tuple[FrontierEntry, ...]:
        entries = build_frontier(baseline=baseline, constraints=constraints, candidates=candidates)
        self.frontiers.replace_for_call_site(tenant_id, call_site_id, entries)
        return entries

    def get_frontier(self, *, tenant_id: TenantId, call_site_id: str) -> tuple[FrontierEntry, ...]:
        return tuple(self.frontiers.list_for_call_site(tenant_id, call_site_id))

    def authorize_deployment(
        self,
        *,
        tenant_id: TenantId,
        deployment_id: str,
        policy: ApplicationPolicy,
        source_config_identity: str,
        target_config: OptimizationConfig,
        authorized_by: str,
        authorized_at: datetime,
    ) -> OptimizationDeployment:
        """Persist a deployment only through the core's explicit opt-in invariant."""
        from valuemaxx.core.optimization import OptimizationDeployment

        deployment = OptimizationDeployment(
            tenant_id=tenant_id,
            id=deployment_id,
            policy=policy,
            source_config_identity=source_config_identity,
            target_config=target_config,
            authorized_by=authorized_by,
            authorized_at=authorized_at,
        )
        self.deployments.upsert(tenant_id, deployment)
        return deployment

    def get_active_deployment(
        self, *, tenant_id: TenantId, call_site_id: str
    ) -> OptimizationDeployment | None:
        return self.deployments.get_active(tenant_id, call_site_id)

    def activate_kill_switch(
        self, *, tenant_id: TenantId, call_site_id: str
    ) -> OptimizationDeployment:
        """Activate the rollback flag on the active deployment."""
        active = self.deployments.get_active(tenant_id, call_site_id)
        if active is None:
            raise ValueError(f"no active deployment for call site {call_site_id!r}")
        killed = active.model_copy(update={"kill_switch_active": True})
        self.deployments.upsert(tenant_id, killed)
        return killed


__all__ = ["OptimizationService"]
