"""Capability-registry projection for lint, search and frontier operations."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from pydantic import BaseModel, Field
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.core import AtmError, TenantId
from valuemaxx.core.optimization import (
    ApplicationMode,
    ApplicationPolicy,
    FrontierEntry,
    OptimizationConfig,
)
from valuemaxx.optimization.linter import PromptBlock, TrafficCall
from valuemaxx.optimization.search import SearchCandidate

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry
    from valuemaxx.core.optimization import OptimizationDeployment
    from valuemaxx.optimization.service import OptimizationService

_SURFACES = Surface.API | Surface.MCP | Surface.CLI


class OptimizationNotWiredError(AtmError):
    """Raised when an optimization handler has no injected service."""


class PromptBlockInput(BaseModel):
    role: str
    content: str


class TrafficCallInput(BaseModel):
    call_id: str
    run_id: str
    request_body: str
    blocks: tuple[PromptBlockInput, ...]


class LintCallSiteInput(BaseModel):
    tenant_id: str
    call_site_id: str
    calls: tuple[TrafficCallInput, ...]


class LintCallSiteOutput(BaseModel):
    finding_count: int
    finding_ids: tuple[str, ...]
    kinds: tuple[str, ...]


class SearchCandidateInput(BaseModel):
    model: str
    provider: str
    estimated_cost: Decimal = Field(ge=Decimal(0))
    scores: dict[int, float]
    reasoning_effort: str | None = None
    max_tokens: int | None = None
    cache_breakpoint: int | None = None
    history_depth: int | None = None

    def config(self) -> OptimizationConfig:
        return OptimizationConfig(
            model=self.model,
            provider=self.provider,
            reasoning_effort=self.reasoning_effort,
            max_tokens=self.max_tokens,
            cache_breakpoint=self.cache_breakpoint,
            history_depth=self.history_depth,
        )


class SearchConfigurationsInput(BaseModel):
    tenant_id: str
    call_site_id: str
    incumbent_cost: Decimal = Field(ge=Decimal(0))
    candidates: tuple[SearchCandidateInput, ...]
    minimum_savings: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)


class SearchConfigurationsOutput(BaseModel):
    survivor_models: tuple[str, ...]
    round_sizes: tuple[int, ...]
    prefiltered_count: int


class GetFrontierInput(BaseModel):
    tenant_id: str
    call_site_id: str


class GetFrontierOutput(BaseModel):
    entries: tuple[FrontierEntry, ...]
    entry_count: int


class AuthorizeDeploymentInput(BaseModel):
    tenant_id: str
    deployment_id: str
    call_site_id: str
    mode: ApplicationMode
    policy_enabled: bool
    source_config_identity: str
    target_model: str
    target_provider: str
    authorized_by: str
    authorized_at: datetime
    reasoning_effort: str | None = None
    max_tokens: int | None = None
    cache_breakpoint: int | None = None
    history_depth: int | None = None


class AuthorizeDeploymentOutput(BaseModel):
    deployment_id: str
    authorized: bool
    kill_switch_active: bool


class GetActiveDeploymentInput(BaseModel):
    tenant_id: str
    call_site_id: str


class GetActiveDeploymentOutput(BaseModel):
    found: bool
    deployment_id: str | None = None
    target_model: str | None = None
    kill_switch_active: bool | None = None
    gateway_policy_json: str | None = None


class ActivateKillSwitchInput(BaseModel):
    tenant_id: str
    call_site_id: str


class ActivateKillSwitchOutput(BaseModel):
    deployment_id: str
    activated: bool


class _Holder:
    __slots__ = ("service",)

    def __init__(self) -> None:
        self.service: OptimizationService | None = None

    def require(self) -> OptimizationService:
        if self.service is None:
            raise OptimizationNotWiredError(
                "optimization capabilities are not wired; call bind_runtime() at startup"
            )
        return self.service


_HOLDERS: WeakKeyDictionary[object, _Holder] = WeakKeyDictionary()


def register(registry: Registry) -> None:
    """Register analysis plus separately authorized deployment operations."""
    holder = _HOLDERS.setdefault(registry, _Holder())

    def lint_handler(request: LintCallSiteInput) -> LintCallSiteOutput:
        tenant = _tenant(request.tenant_id)
        calls = tuple(
            TrafficCall(
                call_id=call.call_id,
                run_id=call.run_id,
                request_body=call.request_body,
                blocks=tuple(
                    PromptBlock(role=block.role, content=block.content) for block in call.blocks
                ),
            )
            for call in request.calls
        )
        findings = holder.require().lint_call_site(
            tenant_id=tenant, call_site_id=request.call_site_id, calls=calls
        )
        return LintCallSiteOutput(
            finding_count=len(findings),
            finding_ids=tuple(finding.id for finding in findings),
            kinds=tuple(finding.kind.value for finding in findings),
        )

    def search_handler(request: SearchConfigurationsInput) -> SearchConfigurationsOutput:
        # Tenant/call-site scope rides the request even though the pure search itself
        # has no persistence side effect.
        inputs = tuple(request.candidates)
        candidates = tuple(
            SearchCandidate(config=item.config(), estimated_cost=item.estimated_cost)
            for item in inputs
        )
        scores_by_identity = {
            candidate.identity: item.scores
            for candidate, item in zip(candidates, inputs, strict=True)
        }

        def evaluate(stage: int, active: tuple[SearchCandidate, ...]) -> dict[str, float]:
            missing = [
                candidate.config.model
                for candidate in active
                if stage not in scores_by_identity[candidate.identity]
            ]
            if missing:
                raise ValueError(f"missing stage {stage} scores for {missing}")
            return {
                candidate.identity: scores_by_identity[candidate.identity][stage]
                for candidate in active
            }

        result = holder.require().search(
            incumbent_cost=request.incumbent_cost,
            candidates=candidates,
            evaluate=evaluate,
            minimum_savings=request.minimum_savings,
        )
        evaluated_first = len(result.rounds[0].evaluated) if result.rounds else 0
        return SearchConfigurationsOutput(
            survivor_models=tuple(candidate.config.model for candidate in result.survivors),
            round_sizes=tuple(len(round_.evaluated) for round_ in result.rounds),
            prefiltered_count=len(candidates) - evaluated_first,
        )

    def frontier_handler(request: GetFrontierInput) -> GetFrontierOutput:
        entries = holder.require().get_frontier(
            tenant_id=_tenant(request.tenant_id), call_site_id=request.call_site_id
        )
        return GetFrontierOutput(entries=entries, entry_count=len(entries))

    def authorize_handler(request: AuthorizeDeploymentInput) -> AuthorizeDeploymentOutput:
        tenant = _tenant(request.tenant_id)
        deployment = holder.require().authorize_deployment(
            tenant_id=tenant,
            deployment_id=request.deployment_id,
            policy=ApplicationPolicy(
                tenant_id=tenant,
                call_site_id=request.call_site_id,
                mode=request.mode,
                enabled=request.policy_enabled,
            ),
            source_config_identity=request.source_config_identity,
            target_config=OptimizationConfig(
                model=request.target_model,
                provider=request.target_provider,
                reasoning_effort=request.reasoning_effort,
                max_tokens=request.max_tokens,
                cache_breakpoint=request.cache_breakpoint,
                history_depth=request.history_depth,
            ),
            authorized_by=request.authorized_by,
            authorized_at=request.authorized_at,
        )
        return AuthorizeDeploymentOutput(
            deployment_id=deployment.id,
            authorized=True,
            kill_switch_active=deployment.kill_switch_active,
        )

    def active_handler(request: GetActiveDeploymentInput) -> GetActiveDeploymentOutput:
        deployment = holder.require().get_active_deployment(
            tenant_id=_tenant(request.tenant_id), call_site_id=request.call_site_id
        )
        if deployment is None:
            return GetActiveDeploymentOutput(found=False)
        return GetActiveDeploymentOutput(
            found=True,
            deployment_id=deployment.id,
            target_model=deployment.target_config.model,
            kill_switch_active=deployment.kill_switch_active,
            gateway_policy_json=_gateway_policy_json(deployment),
        )

    def kill_handler(request: ActivateKillSwitchInput) -> ActivateKillSwitchOutput:
        deployment = holder.require().activate_kill_switch(
            tenant_id=_tenant(request.tenant_id), call_site_id=request.call_site_id
        )
        return ActivateKillSwitchOutput(deployment_id=deployment.id, activated=True)

    registry.register(
        capability(
            name="lint_call_site",
            input_model=LintCallSiteInput,
            output_model=LintCallSiteOutput,
            handler=lint_handler,
            description=(
                "Report structural cache misalignment and exact duplicate calls within a run; "
                "never rewrites prompt semantics."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(
                LintCallSiteInput(
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    call_site_id="support.reply",
                    calls=(),
                ),
            ),
        )
    )
    registry.register(
        capability(
            name="authorize_optimization_deployment",
            input_model=AuthorizeDeploymentInput,
            output_model=AuthorizeDeploymentOutput,
            handler=authorize_handler,
            description=(
                "Authorize a production deployment only from an explicit enabled "
                "per-call-site application policy."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(
                AuthorizeDeploymentInput(
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    deployment_id="deploy-1",
                    call_site_id="support.reply",
                    mode=ApplicationMode.APPROVE,
                    policy_enabled=True,
                    source_config_identity="a" * 64,
                    target_model="claude-haiku-4-5",
                    target_provider="anthropic",
                    authorized_by="user-1",
                    authorized_at=datetime(2026, 8, 22),
                ),
            ),
        )
    )
    registry.register(
        capability(
            name="get_active_optimization_deployment",
            input_model=GetActiveDeploymentInput,
            output_model=GetActiveDeploymentOutput,
            handler=active_handler,
            description="Return the separately authorized active deployment for one call site.",
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(
                GetActiveDeploymentInput(
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    call_site_id="support.reply",
                ),
            ),
        )
    )
    registry.register(
        capability(
            name="activate_optimization_kill_switch",
            input_model=ActivateKillSwitchInput,
            output_model=ActivateKillSwitchOutput,
            handler=kill_handler,
            description=(
                "Activate the call-site kill switch so enforcement reverts to the host's "
                "original configuration."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(
                ActivateKillSwitchInput(
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    call_site_id="support.reply",
                ),
            ),
        )
    )
    registry.register(
        capability(
            name="search_configurations",
            input_model=SearchConfigurationsInput,
            output_model=SearchConfigurationsOutput,
            handler=search_handler,
            description=(
                "Cost-prefilter discrete request configurations, then evaluate all survivors "
                "at 50, 200, and 1000 observed examples while retaining the top half."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(
                SearchConfigurationsInput(
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    call_site_id="support.reply",
                    incumbent_cost=Decimal("0.10"),
                    candidates=(),
                ),
            ),
        )
    )
    registry.register(
        capability(
            name="get_optimization_frontier",
            input_model=GetFrontierInput,
            output_model=GetFrontierOutput,
            handler=frontier_handler,
            description=(
                "Return every retained cost/constraint frontier row for one tenant call site, "
                "including replay-only and failed candidates."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
            examples=(
                GetFrontierInput(
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    call_site_id="support.reply",
                ),
            ),
        )
    )


def bind_runtime(registry: Registry, service: OptimizationService) -> None:
    holder = _HOLDERS.get(registry)
    if holder is None:
        raise OptimizationNotWiredError("call register(registry) before bind_runtime()")
    holder.service = service


def _tenant(value: str) -> TenantId:
    from uuid import UUID

    return TenantId(UUID(value))


def _gateway_policy_json(deployment: OptimizationDeployment) -> str:
    """Render the strict snapshot consumed by the fail-open gateway."""
    patch: dict[str, object] = {"model": deployment.target_config.model}
    if deployment.target_config.reasoning_effort is not None:
        patch["reasoningEffort"] = deployment.target_config.reasoning_effort
    if deployment.target_config.max_tokens is not None:
        patch["maxTokens"] = deployment.target_config.max_tokens
    return json.dumps(
        {
            "id": deployment.id,
            "provider": deployment.target_config.provider,
            "callSiteId": deployment.policy.call_site_id,
            "sourceConfigId": deployment.source_config_identity,
            "rolloutPercent": deployment.ramp_percentage,
            "patch": patch,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "ActivateKillSwitchInput",
    "ActivateKillSwitchOutput",
    "AuthorizeDeploymentInput",
    "AuthorizeDeploymentOutput",
    "GetActiveDeploymentInput",
    "GetActiveDeploymentOutput",
    "GetFrontierInput",
    "GetFrontierOutput",
    "LintCallSiteInput",
    "LintCallSiteOutput",
    "OptimizationNotWiredError",
    "PromptBlockInput",
    "SearchCandidateInput",
    "SearchConfigurationsInput",
    "SearchConfigurationsOutput",
    "TrafficCallInput",
    "bind_runtime",
    "register",
]
