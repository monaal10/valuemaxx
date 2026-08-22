from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from valuemaxx.core import TenantId
from valuemaxx.core.optimization import (
    BaselineCause,
    BaselineStatus,
    CallSiteBaseline,
    ExperimentState,
    OptimizationConfig,
    OptimizationExperiment,
)
from valuemaxx.optimization.baseline import rebaseline_if_dominant

TENANT = TenantId(UUID("22222222-2222-2222-2222-222222222222"))
NOW = datetime(2026, 8, 22, tzinfo=UTC)


def _baseline() -> CallSiteBaseline:
    return CallSiteBaseline(
        tenant_id=TENANT,
        id="base-old",
        call_site_id="site",
        config_identity="a" * 64,
        status=BaselineStatus.ACTIVE,
        dominant_share=Decimal("0.9"),
        outcome_rate=Decimal("0.08"),
        cause=BaselineCause.CUSTOMER_CHANGE,
        activated_at=NOW,
    )


def _experiment(state: ExperimentState) -> OptimizationExperiment:
    return OptimizationExperiment(
        tenant_id=TENANT,
        id=f"exp-{state.value}",
        call_site_id="site",
        baseline_id="base-old",
        candidate=OptimizationConfig(model="cheap", provider="p"),
        state=state,
        ramp_percentage=5,
        started_at=NOW,
    )


def test_new_identity_must_dominate_every_recent_window() -> None:
    result = rebaseline_if_dominant(
        current=_baseline(),
        window_shares=({"b" * 64: Decimal("0.8")}, {"b" * 64: Decimal("0.49")}),
        experiments=(),
        cause=BaselineCause.CUSTOMER_CHANGE,
        now=NOW,
    )
    assert result.changed is False


def test_an_exact_half_is_not_dominance() -> None:
    result = rebaseline_if_dominant(
        current=_baseline(),
        window_shares=({"b" * 64: Decimal("0.5")},),
        experiments=(),
        cause=BaselineCause.CUSTOMER_CHANGE,
        now=NOW,
    )
    assert result.changed is False


def test_rebaseline_retains_superseded_and_invalidates_inflight_experiments() -> None:
    result = rebaseline_if_dominant(
        current=_baseline(),
        window_shares=({"b" * 64: Decimal("0.8")}, {"b" * 64: Decimal("0.7")}),
        experiments=(_experiment(ExperimentState.RUNNING), _experiment(ExperimentState.COMPLETED)),
        cause=BaselineCause.CUSTOMER_CHANGE,
        now=NOW,
    )
    assert result.changed is True
    assert result.superseded is not None
    assert result.superseded.status is BaselineStatus.SUPERSEDED
    assert result.replacement is not None
    assert result.replacement.status is BaselineStatus.BURN_IN
    assert result.replacement.outcome_rate is None
    assert result.experiments[0].state is ExperimentState.INVALIDATED
    assert result.experiments[1].state is ExperimentState.COMPLETED
