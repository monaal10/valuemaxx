"""Unit tests for the sync->async store bridge (drives every sync wrapper method).

The bridge runs the async store on a blocking portal's loop and exposes synchronous
:class:`~valuemaxx.core.repositories.CostEventRepository` /
:class:`~valuemaxx.core.repositories.OutcomeEventRepository` facades. These tests
exercise each wrapper method against a real (temp SQLite) store opened by the bridge
itself (migrations run), and the context-manager lifecycle (engine disposed,
portal stopped on exit).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import CaptureGranularity, Provenance, SignalClass
from valuemaxx.core.ids import (
    AttemptId,
    CostEventId,
    OutcomeEventId,
    RunId,
    TenantId,
)
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
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.run import Run
from valuemaxx.core.tokens import TokenVector
from valuemaxx.server.store_bridge import StoreBridge

if TYPE_CHECKING:
    from pathlib import Path

_AT = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def _tenant() -> TenantId:
    return TenantId(uuid4())


def _cost_event(tenant: TenantId, *, run_id: str, attempt_id: str, cost: str) -> CostEvent:
    return CostEvent(
        tenant_id=tenant,
        id=CostEventId(f"{run_id}:{attempt_id}"),
        run_id=RunId(run_id),
        attempt_id=AttemptId(attempt_id),
        provider="anthropic",
        model="claude-opus-4-8",
        tokens=TokenVector(
            input_uncached=10,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=5,
            reasoning=0,
        ),
        capture_granularity=CaptureGranularity.PER_ATTEMPT,
        provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
        cost_usd=Decimal(cost),
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=False,
        provenance_warnings=(),
        occurred_at=_AT,
    )


def _outcome(tenant: TenantId, *, outcome_id: str, signal: SignalClass) -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=tenant,
        id=OutcomeEventId(outcome_id),
        name="loan_funded",
        signal_class=signal,
        value=Decimal("100.0000000000"),
        occurred_at=_AT,
        binding=OutcomeBinding(run_id=None, tier=None, bound_by=None),
        entity_keys=frozenset({("application", outcome_id)}),
        correlation_id=None,
        source="webhook",
        raw={"amount": 100},
    )


def _run(tenant: TenantId, *, run_id: str, agent_name: str | None) -> Run:
    return Run(
        tenant_id=tenant,
        id=RunId(run_id),
        agent_name=agent_name,
        started_at=_AT,
        ended_at=None,
        entity_keys=frozenset({("application", run_id)}),
    )


def _url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'bridge.db'}"


def test_cost_event_roundtrip_through_sync_wrappers(tmp_path: Path) -> None:
    """test_cost_event_roundtrip_through_sync_wrappers: upsert + list_for_run + window."""
    tenant = _tenant()
    with StoreBridge.open(_url(tmp_path)) as bridge:
        repo = bridge.cost_events
        repo.upsert(tenant, _cost_event(tenant, run_id="r1", attempt_id="a1", cost="0.0100"))
        # at-least-once redelivery upserts on (run_id, attempt_id) -> still one row (M7).
        repo.upsert(tenant, _cost_event(tenant, run_id="r1", attempt_id="a1", cost="0.0100"))

        for_run = repo.list_for_run(tenant, RunId("r1"))
        assert [e.idempotency_key for e in for_run] == [("r1", "a1")]

        window = repo.list_in_window(
            tenant,
            datetime(2026, 6, 27, tzinfo=UTC),
            datetime(2026, 6, 28, tzinfo=UTC),
        )
        assert len(window) == 1
        assert window[0].cost_usd == Decimal("0.0100")


def test_cost_event_tenant_scoping_holds(tmp_path: Path) -> None:
    """test_cost_event_tenant_scoping_holds: a read is scoped to its tenant only."""
    tenant_a, tenant_b = _tenant(), _tenant()
    with StoreBridge.open(_url(tmp_path)) as bridge:
        repo = bridge.cost_events
        repo.upsert(tenant_a, _cost_event(tenant_a, run_id="r1", attempt_id="a1", cost="0.0700"))
        repo.upsert(tenant_b, _cost_event(tenant_b, run_id="r1", attempt_id="a1", cost="9.9900"))

        a_rows = repo.list_for_run(tenant_a, RunId("r1"))
        assert [e.cost_usd for e in a_rows] == [Decimal("0.0700")]


def test_outcome_event_roundtrip_through_sync_wrappers(tmp_path: Path) -> None:
    """test_outcome_event_roundtrip_through_sync_wrappers: upsert + get + retract + list_unbound."""
    tenant = _tenant()
    with StoreBridge.open(_url(tmp_path)) as bridge:
        repo = bridge.outcome_events
        repo.upsert(
            tenant, _outcome(tenant, outcome_id="oe-1", signal=SignalClass.OUTCOME_CONFIRMED)
        )

        fetched = repo.get(tenant, OutcomeEventId("oe-1"))
        assert fetched is not None
        assert fetched.id == "oe-1"

        # unbound (no run) outcomes are the attribution work queue.
        unbound = repo.list_unbound(tenant)
        assert {o.id for o in unbound} == {"oe-1"}

        repo.retract(tenant, OutcomeEventId("oe-1"))
        retracted = repo.get(tenant, OutcomeEventId("oe-1"))
        assert retracted is not None
        assert retracted.signal_class is SignalClass.OUTCOME_RETRACTED


def test_run_roundtrip_through_sync_wrappers(tmp_path: Path) -> None:
    """test_run_roundtrip_through_sync_wrappers: upsert + get + list_by_entity, tenant-scoped."""
    tenant = _tenant()
    with StoreBridge.open(_url(tmp_path)) as bridge:
        repo = bridge.runs
        repo.upsert(tenant, _run(tenant, run_id="r1", agent_name="researcher"))
        repo.upsert(tenant, _run(tenant, run_id="r2", agent_name=None))

        fetched = repo.get(tenant, RunId("r1"))
        assert fetched is not None
        assert fetched.agent_name == "researcher"

        # a run with no agent round-trips a None agent_name (the executor buckets it).
        agentless = repo.get(tenant, RunId("r2"))
        assert agentless is not None
        assert agentless.agent_name is None

        by_entity = repo.list_by_entity(tenant, ("application", "r1"))
        assert {r.id for r in by_entity} == {"r1"}


def test_close_is_idempotent_via_explicit_call(tmp_path: Path) -> None:
    """test_close_is_idempotent_via_explicit_call: open + explicit close disposes cleanly."""
    bridge = StoreBridge.open(_url(tmp_path))
    tenant = _tenant()
    bridge.cost_events.upsert(
        tenant, _cost_event(tenant, run_id="r1", attempt_id="a1", cost="0.0010")
    )
    bridge.close()  # disposes the engine on the portal loop and stops the portal


def test_open_without_migrations_uses_an_existing_schema(tmp_path: Path) -> None:
    """test_open_without_migrations_uses_an_existing_schema: run_migrations toggles alembic."""
    url = _url(tmp_path)
    # first bridge creates the schema via migrations.
    StoreBridge.open(url).close()
    # second bridge reuses it (no second migration run) and still reads/writes.
    tenant = _tenant()
    with StoreBridge.open(url, run_migrations=False) as bridge:
        bridge.cost_events.upsert(
            tenant, _cost_event(tenant, run_id="r2", attempt_id="a2", cost="0.0020")
        )
        assert len(bridge.cost_events.list_for_run(tenant, RunId("r2"))) == 1


def test_optimization_repositories_roundtrip_through_sync_wrappers(tmp_path: Path) -> None:
    """Every optimization port is reachable synchronously through StoreBridge."""
    tenant = _tenant()
    config = OptimizationConfig(model="claude-haiku", provider="anthropic")
    baseline = CallSiteBaseline(
        tenant_id=tenant,
        id="base-1",
        call_site_id="site-a",
        config_identity="a" * 64,
        status=BaselineStatus.ACTIVE,
        dominant_share=Decimal("0.8"),
        outcome_rate=Decimal("0.08"),
        cause=BaselineCause.CUSTOMER_CHANGE,
        activated_at=_AT,
    )
    finding = LinterFinding(
        tenant_id=tenant,
        id="finding-1",
        call_site_id="site-a",
        kind=LinterFindingKind.CACHE_MISALIGNMENT,
        summary="stable prefix follows volatile content",
        evidence="3800 stable tokens over 50 calls",
        evidence_tier=EvidenceTier.STATIC,
    )
    frontier = FrontierEntry(
        config=config,
        metrics=CandidateMetrics(
            cost_per_unit=Decimal("0.07"),
            outcome_rate=Decimal("0.081"),
            error_rate=Decimal("0.01"),
            refusal_rate=Decimal("0.02"),
            p95_latency_ms=800,
            sample_size=9400,
        ),
        evidence_tier=EvidenceTier.LIVE_GUARDRAILS,
        status=CandidateStatus.PASSED,
    )
    experiment = OptimizationExperiment(
        tenant_id=tenant,
        id="exp-1",
        call_site_id="site-a",
        baseline_id="base-1",
        candidate=config,
        state=ExperimentState.RUNNING,
        ramp_percentage=1,
        started_at=_AT,
    )
    deployment = OptimizationDeployment(
        tenant_id=tenant,
        id="deploy-1",
        policy=ApplicationPolicy(
            tenant_id=tenant,
            call_site_id="site-a",
            mode=ApplicationMode.APPROVE,
            enabled=True,
        ),
        source_config_identity="a" * 64,
        target_config=config,
        authorized_by="operator@example.com",
        authorized_at=_AT,
    )

    with StoreBridge.open(_url(tmp_path)) as bridge:
        bridge.optimization_baselines.upsert(tenant, baseline)
        bridge.optimization_findings.upsert(tenant, finding)
        bridge.optimization_frontier.replace_for_call_site(tenant, "site-a", [frontier])
        bridge.optimization_experiments.upsert(tenant, experiment)
        bridge.optimization_deployments.upsert(tenant, deployment)

        assert list(bridge.optimization_baselines.list_for_call_site(tenant, "site-a")) == [
            baseline
        ]
        assert list(bridge.optimization_findings.list_for_call_site(tenant, "site-a")) == [finding]
        assert list(bridge.optimization_frontier.list_for_call_site(tenant, "site-a")) == [frontier]
        assert list(bridge.optimization_experiments.list_for_call_site(tenant, "site-a")) == [
            experiment
        ]
        assert bridge.optimization_deployments.get_active(tenant, "site-a") == deployment


def test_sync_experiment_repository_preserves_active_exclusivity(tmp_path: Path) -> None:
    """The bridge does not weaken the store's one-active-experiment constraint."""
    tenant = _tenant()

    def experiment(experiment_id: str) -> OptimizationExperiment:
        return OptimizationExperiment(
            tenant_id=tenant,
            id=experiment_id,
            call_site_id="site-a",
            baseline_id="base-1",
            candidate=OptimizationConfig(model="claude-haiku", provider="anthropic"),
            state=ExperimentState.RUNNING,
            ramp_percentage=1,
            started_at=_AT,
        )

    with StoreBridge.open(_url(tmp_path)) as bridge:
        bridge.optimization_experiments.upsert(tenant, experiment("exp-1"))
        with pytest.raises(IntegrityError):
            bridge.optimization_experiments.upsert(tenant, experiment("exp-2"))
