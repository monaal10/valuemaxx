"""Continuous-optimization domain contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from valuemaxx.core import TenantId
from valuemaxx.core.optimization import (
    ApplicationMode,
    ApplicationPolicy,
    BaselineCause,
    BaselineStatus,
    CallSiteBaseline,
    CandidateMetrics,
    CandidateStatus,
    ConfigIdentity,
    EvidenceTier,
    ExperimentState,
    FrontierEntry,
    LinterFinding,
    LinterFindingKind,
    OptimizationConfig,
    OptimizationConstraints,
    OptimizationDeployment,
    OptimizationExperiment,
    RollbackSignal,
)


def _config() -> OptimizationConfig:
    return OptimizationConfig(
        model="claude-haiku-4-5",
        provider="anthropic",
        reasoning_effort="low",
        max_tokens=512,
        cache_breakpoint=1,
        history_depth=8,
    )


def test_config_identity_keeps_hashes_separate() -> None:
    identity = ConfigIdentity(
        system_hash="a" * 64,
        tools_hash="b" * 64,
        params_hash="c" * 64,
        template_strength=Decimal("0.94"),
    )
    assert identity.combined != identity.system_hash
    assert identity.combined == "17929a97cbc1ac7a54d3c179c391cd9ec78ff0766f08cb658655727207e7525d"
    assert identity.weak is False


def test_short_hash_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ConfigIdentity(
            system_hash="short",
            tools_hash="b" * 64,
            params_hash="c" * 64,
            template_strength=Decimal("1"),
        )


def test_weak_identity_is_explicit() -> None:
    identity = ConfigIdentity(
        system_hash="a" * 64,
        tools_hash="b" * 64,
        params_hash="c" * 64,
        template_strength=Decimal("0.12"),
    )
    assert identity.weak is True


def test_baseline_burn_in_cannot_claim_measured_rate() -> None:
    with pytest.raises(ValidationError):
        CallSiteBaseline(
            tenant_id=TenantId(uuid4()),
            id="base-1",
            call_site_id="site-1",
            config_identity="f" * 64,
            status=BaselineStatus.BURN_IN,
            dominant_share=Decimal("0.8"),
            outcome_rate=Decimal("0.08"),
            cause=BaselineCause.CUSTOMER_CHANGE,
            activated_at=datetime.now(UTC),
        )


def test_constraints_require_positive_latency_factor() -> None:
    with pytest.raises(ValidationError):
        OptimizationConstraints(
            outcome_margin=Decimal("0.01"),
            max_latency_factor=Decimal("0"),
        )


def test_frontier_entry_cannot_pass_with_failed_constraint() -> None:
    with pytest.raises(ValidationError):
        FrontierEntry(
            config=_config(),
            metrics=CandidateMetrics(
                cost_per_unit=Decimal("0.052"),
                outcome_rate=Decimal("0.079"),
                error_rate=Decimal("0.001"),
                refusal_rate=Decimal("0.001"),
                p95_latency_ms=900,
                sample_size=1000,
            ),
            evidence_tier=EvidenceTier.REPLAY,
            status=CandidateStatus.PASSED,
            failed_constraints=("latency",),
        )


def test_application_policy_is_per_call_site_and_ramped() -> None:
    policy = ApplicationPolicy(
        tenant_id=TenantId(uuid4()),
        call_site_id="site-1",
        mode=ApplicationMode.AUTO,
        enabled=True,
        ramp_percentages=(1, 5, 25, 100),
    )
    assert policy.ramp_percentages == (1, 5, 25, 100)
    with pytest.raises(ValidationError):
        ApplicationPolicy(
            tenant_id=policy.tenant_id,
            call_site_id="site-1",
            mode=ApplicationMode.AUTO,
            enabled=True,
            ramp_percentages=(5, 100),
        )


def test_linter_finding_is_structural_and_evidence_labeled() -> None:
    finding = LinterFinding(
        tenant_id=TenantId(uuid4()),
        id="finding-1",
        call_site_id="site-1",
        kind=LinterFindingKind.CACHE_MISALIGNMENT,
        summary="Stable prefix follows volatile content",
        evidence="3,800 of 4,200 tokens were stable across 50 calls",
        evidence_tier=EvidenceTier.STATIC,
        estimated_savings_usd=Decimal("12.30"),
    )
    assert finding.evidence_tier is EvidenceTier.STATIC


def test_outcome_rate_cannot_be_a_fast_rollback_signal() -> None:
    assert {signal.value for signal in RollbackSignal} == {
        "error_rate",
        "refusal_rate",
        "parse_failure_rate",
        "p95_latency",
    }


def test_only_one_change_is_encoded_in_an_experiment() -> None:
    experiment = OptimizationExperiment(
        tenant_id=TenantId(uuid4()),
        id="experiment-1",
        call_site_id="site-1",
        baseline_id="baseline-1",
        candidate=_config(),
        state=ExperimentState.RUNNING,
        ramp_percentage=5,
        started_at=datetime.now(UTC),
    )
    assert experiment.ramp_percentage == 5
    with pytest.raises(ValidationError):
        OptimizationExperiment(
            tenant_id=experiment.tenant_id,
            id="experiment-2",
            call_site_id="site-1",
            baseline_id="baseline-1",
            candidate=_config(),
            state=ExperimentState.RUNNING,
            ramp_percentage=10,
            started_at=datetime.now(UTC),
        )


def test_deployment_requires_explicit_enabled_policy() -> None:
    disabled = ApplicationPolicy(
        tenant_id=TenantId(uuid4()),
        call_site_id="site-1",
        mode=ApplicationMode.APPROVE,
        enabled=False,
    )
    with pytest.raises(ValidationError):
        OptimizationDeployment(
            tenant_id=disabled.tenant_id,
            id="deploy-1",
            policy=disabled,
            source_config_identity="a" * 64,
            target_config=_config(),
            authorized_by="user-1",
            authorized_at=datetime.now(UTC),
        )


def test_deployment_starts_at_one_percent_ramp() -> None:
    policy = ApplicationPolicy(
        tenant_id=TenantId(uuid4()),
        call_site_id="site-1",
        mode=ApplicationMode.APPROVE,
        enabled=True,
    )
    deployment = OptimizationDeployment(
        tenant_id=policy.tenant_id,
        id="deploy-1",
        policy=policy,
        source_config_identity="a" * 64,
        target_config=_config(),
        authorized_by="user-1",
        authorized_at=datetime.now(UTC),
    )
    assert deployment.ramp_percentage == 1
