from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from typing_extensions import override
from valuemaxx.capabilities import Mode, Registry, Surface
from valuemaxx.core import TenantId
from valuemaxx.core.optimization import ApplicationMode
from valuemaxx.core.optimization_repositories import (
    DeploymentRepository,
    FindingRepository,
    FrontierRepository,
)
from valuemaxx.optimization.capabilities import (
    ActivateKillSwitchInput,
    ActivateKillSwitchOutput,
    AuthorizeDeploymentInput,
    AuthorizeDeploymentOutput,
    GetActiveDeploymentInput,
    GetActiveDeploymentOutput,
    GetFrontierInput,
    LintCallSiteInput,
    LintCallSiteOutput,
    OptimizationNotWiredError,
    PromptBlockInput,
    SearchCandidateInput,
    SearchConfigurationsInput,
    SearchConfigurationsOutput,
    TrafficCallInput,
    bind_runtime,
    register,
)
from valuemaxx.optimization.service import OptimizationService

if TYPE_CHECKING:
    from collections.abc import Sequence

    from valuemaxx.core.optimization import (
        FrontierEntry,
        LinterFinding,
        OptimizationDeployment,
    )

TENANT = TenantId(UUID("33333333-3333-3333-3333-333333333333"))


class Findings(FindingRepository):
    def __init__(self) -> None:
        self.rows: list[LinterFinding] = []

    @override
    def upsert(self, tenant_id: TenantId, finding: LinterFinding) -> None:
        assert tenant_id == finding.tenant_id
        self.rows.append(finding)

    @override
    def list_for_call_site(self, tenant_id: TenantId, call_site_id: str) -> Sequence[LinterFinding]:
        return [f for f in self.rows if f.tenant_id == tenant_id and f.call_site_id == call_site_id]


class Frontiers(FrontierRepository):
    def __init__(self) -> None:
        self.rows: dict[tuple[TenantId, str], tuple[FrontierEntry, ...]] = {}

    @override
    def replace_for_call_site(
        self, tenant_id: TenantId, call_site_id: str, entries: Sequence[FrontierEntry]
    ) -> None:
        self.rows[(tenant_id, call_site_id)] = tuple(entries)

    @override
    def list_for_call_site(self, tenant_id: TenantId, call_site_id: str) -> Sequence[FrontierEntry]:
        return self.rows.get((tenant_id, call_site_id), ())


class Deployments(DeploymentRepository):
    def __init__(self) -> None:
        self.rows: dict[tuple[TenantId, str], OptimizationDeployment] = {}

    @override
    def upsert(self, tenant_id: TenantId, deployment: OptimizationDeployment) -> None:
        self.rows[(tenant_id, deployment.policy.call_site_id)] = deployment

    @override
    def get_active(self, tenant_id: TenantId, call_site_id: str) -> OptimizationDeployment | None:
        return self.rows.get((tenant_id, call_site_id))


def _wired() -> tuple[Registry, Findings, Frontiers, Deployments]:
    findings, frontiers, deployments = Findings(), Frontiers(), Deployments()
    registry = Registry()
    register(registry)
    bind_runtime(
        registry,
        OptimizationService(findings=findings, frontiers=frontiers, deployments=deployments),
    )
    return registry, findings, frontiers, deployments


def test_registers_lint_search_and_frontier_on_all_request_surfaces() -> None:
    registry = Registry()
    register(registry)
    assert {spec.name for spec in registry.all()} == {
        "activate_optimization_kill_switch",
        "authorize_optimization_deployment",
        "get_active_optimization_deployment",
        "lint_call_site",
        "search_configurations",
        "get_optimization_frontier",
    }
    for spec in registry.all():
        assert spec.mode is Mode.REQUEST_RESPONSE
        assert spec.surfaces == Surface.API | Surface.MCP | Surface.CLI
        assert spec.examples


def test_unwired_handler_raises() -> None:
    registry = Registry()
    register(registry)
    handler = next(s.handler for s in registry.all() if s.name == "get_optimization_frontier")
    with pytest.raises(OptimizationNotWiredError):
        handler(GetFrontierInput(tenant_id=str(TENANT), call_site_id="site"))


def test_lint_capability_persists_findings() -> None:
    registry, findings, _, _ = _wired()
    handler = next(s.handler for s in registry.all() if s.name == "lint_call_site")
    out = cast(
        "LintCallSiteOutput",
        handler(
            LintCallSiteInput(
                tenant_id=str(TENANT),
                call_site_id="site",
                calls=(
                    TrafficCallInput(
                        call_id="1",
                        run_id="r",
                        request_body="same",
                        blocks=(PromptBlockInput(role="system", content="stable"),),
                    ),
                    TrafficCallInput(
                        call_id="2",
                        run_id="r",
                        request_body="same",
                        blocks=(PromptBlockInput(role="system", content="stable"),),
                    ),
                ),
            ),
        ),
    )
    assert out.finding_count == 1
    assert len(findings.rows) == 1


def test_search_capability_prefilters_then_halves() -> None:
    registry, _, _, _ = _wired()
    handler = next(s.handler for s in registry.all() if s.name == "search_configurations")
    candidates = tuple(
        SearchCandidateInput(
            model=str(i),
            provider="p",
            estimated_cost=Decimal(f"0.{i + 1}"),
            scores={50: float(i), 200: float(i), 1000: float(i)},
        )
        for i in range(7)
    )
    out = cast(
        "SearchConfigurationsOutput",
        handler(
            SearchConfigurationsInput(
                tenant_id=str(TENANT),
                call_site_id="site",
                incumbent_cost=Decimal("1"),
                candidates=candidates,
            )
        ),
    )
    assert out.round_sizes == (7, 4, 2)
    assert out.survivor_models == ("6",)


def test_authorize_get_and_kill_switch_are_separate_control_plane_operations() -> None:
    registry, _, _, deployments = _wired()
    authorize = next(
        s.handler for s in registry.all() if s.name == "authorize_optimization_deployment"
    )
    authorized = cast(
        "AuthorizeDeploymentOutput",
        authorize(
            AuthorizeDeploymentInput(
                tenant_id=str(TENANT),
                deployment_id="deploy-1",
                call_site_id="site",
                mode=ApplicationMode.APPROVE,
                policy_enabled=True,
                source_config_identity="a" * 64,
                target_model="cheap",
                target_provider="p",
                authorized_by="user-1",
                authorized_at=datetime(2026, 8, 22, tzinfo=UTC),
            )
        ),
    )
    assert authorized.authorized is True
    assert deployments.get_active(TENANT, "site") is not None

    get_active = next(
        s.handler for s in registry.all() if s.name == "get_active_optimization_deployment"
    )
    active = cast(
        "GetActiveDeploymentOutput",
        get_active(GetActiveDeploymentInput(tenant_id=str(TENANT), call_site_id="site")),
    )
    assert active.found is True
    assert active.kill_switch_active is False
    assert json.loads(active.gateway_policy_json or "") == {
        "id": "deploy-1",
        "provider": "p",
        "callSiteId": "site",
        "sourceConfigId": "a" * 64,
        "rolloutPercent": 1,
        "patch": {"model": "cheap"},
    }

    kill = next(s.handler for s in registry.all() if s.name == "activate_optimization_kill_switch")
    killed = cast(
        "ActivateKillSwitchOutput",
        kill(ActivateKillSwitchInput(tenant_id=str(TENANT), call_site_id="site")),
    )
    assert killed.activated is True
    stored = deployments.get_active(TENANT, "site")
    assert stored is not None
    assert stored.kill_switch_active is True


def test_authorization_rejects_disabled_policy() -> None:
    registry, _, _, _ = _wired()
    authorize = next(
        s.handler for s in registry.all() if s.name == "authorize_optimization_deployment"
    )
    with pytest.raises(ValueError, match="opt-in"):
        authorize(
            AuthorizeDeploymentInput(
                tenant_id=str(TENANT),
                deployment_id="deploy-1",
                call_site_id="site",
                mode=ApplicationMode.APPROVE,
                policy_enabled=False,
                source_config_identity="a" * 64,
                target_model="cheap",
                target_provider="p",
                authorized_by="user-1",
                authorized_at=datetime(2026, 8, 22, tzinfo=UTC),
            )
        )
