"""Intra-package integration: ingest CostEvents -> a query capability returns a rollup.

This wires the REAL query path against a REAL (temp SQLite) store opened by the
:class:`~valuemaxx.server.store_bridge.StoreBridge`: the concrete async repositories
(behind synchronous facades) feed the real
:class:`~valuemaxx.metrics.executor.MetricExecutor`. We persist a few ``CostEvent``
rows (and the ``Run``/``OutcomeEvent`` rows the join/denominator need), run the
metrics query, and assert the rollup is correct and carries both H7 confidence
fields per cell (``minimum_tier`` + ``confidence_distribution``):

* cost-by-model — one cell per model, summed from the store;
* cost-by-agent — cost resolved through the run join (a ``CostEvent`` has no agent,
  so the executor reads ``Run.agent_name`` via the run repo), one cell per agent;
* cost-per-outcome WHERE OUTCOMES EXIST — total cost over the billing-grade
  ``verified_outcome_count`` denominator, with a non-``None`` ratio and the H7
  distribution reflecting the actual bound tiers;
* tenant scoping — the rollup never sees another tenant's persisted cost.

These run the executor directly over the bridge repos (not the HTTP wire — that is
``test_e2e.py``), so the persistence-backed rollup math is proven end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from valuemaxx.core import MetricDefinition
from valuemaxx.core.cost import CostEvent
from valuemaxx.core.enums import BindingTier, CaptureGranularity, Provenance, SignalClass
from valuemaxx.core.ids import (
    AttemptId,
    CostEventId,
    OutcomeEventId,
    RunId,
    TenantId,
)
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.rollup import RollupConfidence
from valuemaxx.core.run import Run
from valuemaxx.core.tokens import TokenVector
from valuemaxx.metrics.compiler import QueryPlan, compile_plan
from valuemaxx.metrics.executor import MetricExecutor, MetricWindow
from valuemaxx.server.store_bridge import StoreBridge

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

import pytest

_AT = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
_WINDOW = MetricWindow(
    start=datetime(2026, 6, 1, tzinfo=UTC),
    end=datetime(2026, 7, 1, tzinfo=UTC),
)


def _cost(
    tenant: TenantId,
    *,
    run_id: str,
    attempt_id: str,
    usd: str,
    provider: str = "anthropic",
    model: str = "claude-opus-4-8",
) -> CostEvent:
    return CostEvent(
        tenant_id=tenant,
        id=CostEventId(f"{run_id}:{attempt_id}"),
        run_id=RunId(run_id),
        attempt_id=AttemptId(attempt_id),
        provider=provider,
        model=model,
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
        cost_usd=Decimal(usd),
        is_streaming=False,
        partial_recovered=False,
        billing_uncertain_abort=False,
        provenance_warnings=(),
        occurred_at=_AT,
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


def _outcome(
    tenant: TenantId,
    *,
    outcome_id: str,
    signal: SignalClass,
    tier: BindingTier | None,
) -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=tenant,
        id=OutcomeEventId(outcome_id),
        name="loan_funded",
        signal_class=signal,
        value=Decimal("1"),
        occurred_at=_AT,
        binding=OutcomeBinding(
            run_id=None,
            tier=tier,
            bound_by="attribution" if tier is not None else None,
        ),
        entity_keys=frozenset({("application", outcome_id)}),
        correlation_id=None,
        source="webhook",
        raw={"amount": 1},
    )


def _plan(name: str, *, numerator: str, denominator: str, group_by: tuple[str, ...]) -> QueryPlan:
    return compile_plan(
        MetricDefinition(
            name=name,
            numerator=numerator,
            denominator=denominator,
            filters={},
            group_by=group_by,
        )
    )


@pytest.fixture
def tenant() -> TenantId:
    """The tenant the rollup is scoped to."""
    return TenantId(uuid4())


@pytest.fixture
def bridge(tmp_path: Path) -> Iterator[StoreBridge]:
    """A real store bridge over a fresh temp SQLite DB (migrations run on open)."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'rollup.db'}"
    with StoreBridge.open(url) as opened:
        yield opened


def _executor(bridge: StoreBridge) -> MetricExecutor:
    return MetricExecutor(
        cost_repo=bridge.cost_events,
        outcome_repo=bridge.outcome_events,
        run_repo=bridge.runs,
    )


def test_cost_by_model_rollup_from_the_store(bridge: StoreBridge, tenant: TenantId) -> None:
    """Ingest CostEvents on two models -> one rollup cell per model, summed from the store."""
    bridge.cost_events.upsert(tenant, _cost(tenant, run_id="r1", attempt_id="a1", usd="0.0250"))
    bridge.cost_events.upsert(tenant, _cost(tenant, run_id="r1", attempt_id="a2", usd="0.0150"))
    bridge.cost_events.upsert(
        tenant, _cost(tenant, run_id="r2", attempt_id="a3", usd="0.0400", model="claude-haiku")
    )

    plan = _plan(
        "cost_by_model",
        numerator="total_cost_usd",
        denominator="verified_outcome_count",
        group_by=("model",),
    )
    result = _executor(bridge).run(tenant, plan, _WINDOW, ())

    by_model = {dict(cell.group_key)["model"]: cell for cell in result.cells}
    assert set(by_model) == {"claude-opus-4-8", "claude-haiku"}
    # 0.0250 + 0.0150 on opus; 0.0400 on haiku — summed straight from the store rows.
    assert by_model["claude-opus-4-8"].numerator_value == Decimal("0.0400")
    assert by_model["claude-haiku"].numerator_value == Decimal("0.0400")
    # every cell carries both H7 fields (no surface can collapse them).
    for cell in result.cells:
        assert isinstance(cell.confidence, RollupConfidence)
        assert cell.confidence.minimum_tier is not None
        assert cell.confidence.confidence_distribution


def test_cost_by_agent_rollup_resolves_the_run_join(bridge: StoreBridge, tenant: TenantId) -> None:
    """Ingest CostEvents + Runs -> cost-by-agent resolves run.agent_name from the store."""
    bridge.runs.upsert(tenant, _run(tenant, run_id="r1", agent_name="researcher"))
    bridge.runs.upsert(tenant, _run(tenant, run_id="r2", agent_name="writer"))
    bridge.cost_events.upsert(tenant, _cost(tenant, run_id="r1", attempt_id="a1", usd="0.0600"))
    bridge.cost_events.upsert(tenant, _cost(tenant, run_id="r2", attempt_id="a2", usd="0.0400"))
    # a cost event whose run was never persisted buckets under "unknown" (never dropped).
    bridge.cost_events.upsert(tenant, _cost(tenant, run_id="r3", attempt_id="a3", usd="0.0100"))

    plan = _plan(
        "cost_by_agent",
        numerator="total_cost_usd",
        denominator="verified_outcome_count",
        group_by=("agent_name",),
    )
    result = _executor(bridge).run(tenant, plan, _WINDOW, ())

    by_agent = {dict(cell.group_key)["agent_name"]: cell for cell in result.cells}
    assert set(by_agent) == {"researcher", "writer", "unknown"}
    assert by_agent["researcher"].numerator_value == Decimal("0.0600")
    assert by_agent["writer"].numerator_value == Decimal("0.0400")
    assert by_agent["unknown"].numerator_value == Decimal("0.0100")
    for cell in result.cells:
        assert cell.confidence.minimum_tier is not None
        assert cell.confidence.confidence_distribution


def test_cost_per_outcome_where_outcomes_exist(bridge: StoreBridge, tenant: TenantId) -> None:
    """Ingest CostEvents + bound OutcomeEvents -> a correct cost-per-outcome ratio + H7.

    Two confirmed outcomes are bound at billing-grade tiers (exact + deterministic),
    one confirmed outcome is only a candidate (advisory, excluded from the
    billing-grade denominator but counted in the H7 distribution). The ratio is the
    summed store cost over the 2 verified outcomes; the confidence headline is the
    least-trusted contributing tier (CANDIDATE).
    """
    bridge.cost_events.upsert(tenant, _cost(tenant, run_id="r1", attempt_id="a1", usd="6.00"))
    bridge.outcome_events.upsert(
        tenant,
        _outcome(
            tenant, outcome_id="oe-1", signal=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT
        ),
    )
    bridge.outcome_events.upsert(
        tenant,
        _outcome(
            tenant,
            outcome_id="oe-2",
            signal=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
        ),
    )
    bridge.outcome_events.upsert(
        tenant,
        _outcome(
            tenant,
            outcome_id="oe-3",
            signal=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.CANDIDATE,
        ),
    )

    # the runtime fetches outcomes from the store within the tenant scope (here the
    # unbound work queue covers them all) and hands the bound set to the executor.
    outcomes = bridge.outcome_events.list_unbound(tenant)
    plan = _plan(
        "cost_per_outcome",
        numerator="total_cost_usd",
        denominator="verified_outcome_count",
        group_by=(),
    )
    result = _executor(bridge).run(tenant, plan, _WINDOW, outcomes)

    cell = result.cells[0]
    assert cell.numerator_value == Decimal("6.00")
    assert cell.denominator_value == 2  # only the exact + deterministic outcomes count (H8)
    assert cell.value == Decimal("3.00")  # 6.00 / 2 verified
    assert cell.advisory_excluded_count == 1  # the candidate is excluded-but-counted
    # H7: the headline is the least-trusted contributing tier; the distribution keeps all.
    assert cell.confidence.minimum_tier is BindingTier.CANDIDATE
    assert cell.confidence.confidence_distribution[BindingTier.EXACT] == 1
    assert cell.confidence.confidence_distribution[BindingTier.DETERMINISTIC] == 1
    assert cell.confidence.confidence_distribution[BindingTier.CANDIDATE] == 1


def test_rollup_is_tenant_scoped(bridge: StoreBridge, tenant: TenantId) -> None:
    """Another tenant's persisted cost never enters this tenant's rollup."""
    other = TenantId(uuid4())
    bridge.cost_events.upsert(tenant, _cost(tenant, run_id="r1", attempt_id="a1", usd="0.0700"))
    bridge.cost_events.upsert(other, _cost(other, run_id="r1", attempt_id="a1", usd="9.9900"))

    plan = _plan(
        "cost_total",
        numerator="total_cost_usd",
        denominator="verified_outcome_count",
        group_by=(),
    )
    result = _executor(bridge).run(tenant, plan, _WINDOW, ())
    cell = result.cells[0]
    assert cell.numerator_value == Decimal("0.0700")  # only this tenant's cost
