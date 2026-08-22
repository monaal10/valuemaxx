"""Typed contracts for continuous configuration optimization.

The optimizer changes only provider request configuration. Structural linter findings
remain separate artifacts, and every candidate states the evidence tier it has earned.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import IntEnum, StrEnum

from pydantic import Field, computed_field, model_validator
from valuemaxx.core.base import StrictModel, TenantScopedModel

_Hash = str
_RAMP = (1, 5, 25, 100)


class EvidenceTier(IntEnum):
    """Evidence ladder; a tier may be earned only after all lower tiers."""

    STATIC = 1
    REPLAY = 2
    LIVE_GUARDRAILS = 3
    OUTCOME_NON_INFERIORITY = 4


class LinterFindingKind(StrEnum):
    """Structural facts the linter can report without interpreting semantics."""

    CACHE_MISALIGNMENT = "cache_misalignment"
    DUPLICATE_CALL = "duplicate_call"
    REPEATED_TOOL_BLOCK = "repeated_tool_block"
    UNUSED_RETRIEVAL = "unused_retrieval"
    WEAK_CONFIG_IDENTITY = "weak_config_identity"


class BaselineStatus(StrEnum):
    """Lifecycle state of a derived call-site baseline."""

    BURN_IN = "burn_in"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class BaselineCause(StrEnum):
    """Why a newly dominant baseline appeared."""

    CUSTOMER_CHANGE = "customer_change"
    APPLIED_CANDIDATE = "applied_candidate"


class CandidateStatus(StrEnum):
    """Current disposition of a candidate configuration."""

    PREFILTERED = "prefiltered"
    EVALUATING = "evaluating"
    PASSED = "passed"
    FAILED = "failed"
    INVALIDATED = "invalidated"


class ApplicationMode(StrEnum):
    """Who authorizes a candidate after it earns sufficient evidence."""

    APPROVE = "approve"
    AUTO = "auto"


class ExperimentState(StrEnum):
    """Lifecycle of one exclusive experiment at a call site."""

    PENDING = "pending"
    RUNNING = "running"
    HELD = "held"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    INVALIDATED = "invalidated"


class RollbackSignal(StrEnum):
    """Fast signals allowed to trigger rollback; delayed outcomes are excluded."""

    ERROR_RATE = "error_rate"
    REFUSAL_RATE = "refusal_rate"
    PARSE_FAILURE_RATE = "parse_failure_rate"
    P95_LATENCY = "p95_latency"


class ConfigIdentity(StrictModel):
    """Gateway-computed identity with independently attributable hashes."""

    system_hash: _Hash = Field(pattern=r"^[0-9a-f]{64}$")
    tools_hash: _Hash = Field(pattern=r"^[0-9a-f]{64}$")
    params_hash: _Hash = Field(pattern=r"^[0-9a-f]{64}$")
    template_strength: Decimal = Field(ge=Decimal(0), le=Decimal(1))

    @computed_field
    @property
    def combined(self) -> str:
        """Stable identity for grouping while preserving component attribution."""
        material = json.dumps(
            {
                "systemHash": self.system_hash,
                "toolsHash": self.tools_hash,
                "paramsHash": self.params_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode()).hexdigest()

    @computed_field
    @property
    def weak(self) -> bool:
        """Whether dynamic content overwhelmed the inferred system template."""
        return self.template_strength < Decimal("0.3")


class OptimizationConfig(StrictModel):
    """One request-body configuration in the discrete search space."""

    model: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    reasoning_effort: str | None = None
    max_tokens: int | None = Field(default=None, gt=0)
    cache_breakpoint: int | None = Field(default=None, ge=0)
    history_depth: int | None = Field(default=None, ge=0)


class OptimizationConstraints(StrictModel):
    """Customer-stated quality and latency bounds; cost remains the objective."""

    outcome_margin: Decimal = Field(ge=Decimal(0), le=Decimal(1))
    max_latency_factor: Decimal = Field(gt=Decimal(0))
    error_rate_may_increase: bool = False
    refusal_rate_may_increase: bool = False


class CandidateMetrics(StrictModel):
    """Observed metrics for a candidate at one evidence tier."""

    cost_per_unit: Decimal = Field(ge=Decimal(0))
    outcome_rate: Decimal | None = Field(default=None, ge=Decimal(0), le=Decimal(1))
    error_rate: Decimal = Field(ge=Decimal(0), le=Decimal(1))
    refusal_rate: Decimal = Field(ge=Decimal(0), le=Decimal(1))
    p95_latency_ms: int = Field(ge=0)
    sample_size: int = Field(ge=0)


class FrontierEntry(StrictModel):
    """One honest row of the cost/quality evidence frontier."""

    config: OptimizationConfig
    metrics: CandidateMetrics
    evidence_tier: EvidenceTier
    status: CandidateStatus
    failed_constraints: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _passed_means_no_failed_constraint(self) -> FrontierEntry:
        if self.status is CandidateStatus.PASSED and self.failed_constraints:
            raise ValueError("a passed candidate cannot carry failed constraints")
        return self


class CallSiteBaseline(TenantScopedModel):
    """A derived, retained baseline for one discovered call site."""

    id: str = Field(min_length=1)
    call_site_id: str = Field(min_length=1)
    config_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: BaselineStatus
    dominant_share: Decimal = Field(ge=Decimal(0), le=Decimal(1))
    outcome_rate: Decimal | None = Field(default=None, ge=Decimal(0), le=Decimal(1))
    cause: BaselineCause
    activated_at: datetime

    @model_validator(mode="after")
    def _burn_in_has_no_rate(self) -> CallSiteBaseline:
        if self.status is BaselineStatus.BURN_IN and self.outcome_rate is not None:
            raise ValueError("a burn-in baseline cannot anchor an outcome-rate test")
        return self


class LinterFinding(TenantScopedModel):
    """A structural finding for human action, separate from applyable configs."""

    id: str = Field(min_length=1)
    call_site_id: str = Field(min_length=1)
    kind: LinterFindingKind
    summary: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    evidence_tier: EvidenceTier
    estimated_savings_usd: Decimal | None = Field(default=None, ge=Decimal(0))

    @model_validator(mode="after")
    def _findings_are_static(self) -> LinterFinding:
        if self.evidence_tier is not EvidenceTier.STATIC:
            raise ValueError("structural linter findings earn only the static tier")
        return self


class ApplicationPolicy(TenantScopedModel):
    """Explicit per-call-site opt-in and the mandatory progressive ramp."""

    call_site_id: str = Field(min_length=1)
    mode: ApplicationMode
    enabled: bool = False
    ramp_percentages: tuple[int, ...] = _RAMP

    @model_validator(mode="after")
    def _fixed_safe_ramp(self) -> ApplicationPolicy:
        if self.ramp_percentages != _RAMP:
            raise ValueError("application ramp must be exactly 1% -> 5% -> 25% -> 100%")
        return self


class OptimizationExperiment(TenantScopedModel):
    """One candidate change tested exclusively against one retained baseline."""

    id: str = Field(min_length=1)
    call_site_id: str = Field(min_length=1)
    baseline_id: str = Field(min_length=1)
    candidate: OptimizationConfig
    state: ExperimentState
    ramp_percentage: int
    started_at: datetime
    invalidation_reason: str | None = None
    rollback_signal: RollbackSignal | None = None

    @model_validator(mode="after")
    def _valid_ramp_and_terminal_reason(self) -> OptimizationExperiment:
        if self.ramp_percentage not in _RAMP:
            raise ValueError("experiment ramp must be one of 1%, 5%, 25%, or 100%")
        if self.state is ExperimentState.INVALIDATED and not self.invalidation_reason:
            raise ValueError("an invalidated experiment must retain its reason")
        if self.state is ExperimentState.ROLLED_BACK and self.rollback_signal is None:
            raise ValueError("a rolled-back experiment must name its fast signal")
        return self


class OptimizationDeployment(TenantScopedModel):
    """A separately authorized production deployment; recommendations stay evidence."""

    id: str = Field(min_length=1)
    policy: ApplicationPolicy
    source_config_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_config: OptimizationConfig
    authorized_by: str = Field(min_length=1)
    authorized_at: datetime
    ramp_percentage: int = 1
    kill_switch_active: bool = False

    @model_validator(mode="after")
    def _requires_explicit_matching_opt_in(self) -> OptimizationDeployment:
        if not self.policy.enabled:
            raise ValueError("deployment requires explicit per-call-site opt-in")
        if self.policy.tenant_id != self.tenant_id:
            raise ValueError("deployment and policy tenant must match")
        if self.ramp_percentage not in _RAMP:
            raise ValueError("deployment ramp must be one of 1%, 5%, 25%, or 100%")
        return self


__all__ = [
    "ApplicationMode",
    "ApplicationPolicy",
    "BaselineCause",
    "BaselineStatus",
    "CallSiteBaseline",
    "CandidateMetrics",
    "CandidateStatus",
    "ConfigIdentity",
    "EvidenceTier",
    "ExperimentState",
    "FrontierEntry",
    "LinterFinding",
    "LinterFindingKind",
    "OptimizationConfig",
    "OptimizationConstraints",
    "OptimizationDeployment",
    "OptimizationExperiment",
    "RollbackSignal",
]
