"""Executor tests — run a compiled plan against in-memory repo ABCs.

The executor consumes a :class:`~valuemaxx.metrics.compiler.QueryPlan`, reads cost
events from the injected :class:`~valuemaxx.core.CostEventRepository` over a window,
applies the H8 denominator semantics to the supplied outcomes, and produces a
:class:`~valuemaxx.metrics.schemas.MetricResult` carrying both H7 fields and the
H8 exclusion counts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from _metrics_helpers import (
    InMemoryCostEventRepository,
    InMemoryOutcomeEventRepository,
    InMemoryRunRepository,
)
from valuemaxx.core import (
    AttemptId,
    BindingTier,
    CaptureGranularity,
    CostEvent,
    CostEventId,
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    Provenance,
    ProvenanceLabel,
    RollupConfidence,
    Run,
    RunId,
    SignalClass,
    TenantId,
    TokenVector,
)
from valuemaxx.metrics.compiler import compile_plan
from valuemaxx.metrics.executor import MetricExecutor, MetricWindow
from valuemaxx.metrics.schemas import MetricCell, MetricResult

_TENANT = TenantId(uuid4())
_WINDOW = MetricWindow(
    start=datetime(2026, 6, 1, tzinfo=UTC),
    end=datetime(2026, 7, 1, tzinfo=UTC),
)


def _cost(run: str, *, usd: str, provider: str = "anthropic", model: str = "opus") -> CostEvent:
    return CostEvent(
        tenant_id=_TENANT,
        id=CostEventId(f"ce-{uuid4()}"),
        run_id=RunId(run),
        attempt_id=AttemptId(f"at-{uuid4()}"),
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
        occurred_at=datetime(2026, 6, 15, tzinfo=UTC),
    )


def _outcome(*, signal_class: SignalClass, tier: BindingTier | None) -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=_TENANT,
        id=OutcomeEventId(f"oe-{uuid4()}"),
        name="signup",
        signal_class=signal_class,
        value=Decimal("1"),
        occurred_at=datetime(2026, 6, 15, tzinfo=UTC),
        binding=OutcomeBinding(run_id=None, tier=tier, bound_by="t1" if tier else None),
        entity_keys=frozenset(),
        correlation_id=None,
        source="test",
        raw={},
    )


def _run(run: str, *, agent_name: str | None) -> Run:
    return Run(
        tenant_id=_TENANT,
        id=RunId(run),
        agent_name=agent_name,
        started_at=datetime(2026, 6, 15, tzinfo=UTC),
        ended_at=None,
        entity_keys=frozenset(),
    )


def _executor() -> tuple[
    MetricExecutor,
    InMemoryCostEventRepository,
    InMemoryOutcomeEventRepository,
    InMemoryRunRepository,
]:
    costs = InMemoryCostEventRepository()
    outcomes = InMemoryOutcomeEventRepository()
    runs = InMemoryRunRepository()
    executor = MetricExecutor(cost_repo=costs, outcome_repo=outcomes, run_repo=runs)
    return executor, costs, outcomes, runs


def test_cost_per_outcome_end_to_end() -> None:
    """2 exact + 3 candidate confirmed outcomes -> denominator 2; cost summed."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    for tier in (BindingTier.EXACT, BindingTier.EXACT):
        outcomes.upsert(_TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=tier))
    for _ in range(3):
        outcomes.upsert(
            _TENANT,
            _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.CANDIDATE),
        )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    assert isinstance(result, MetricResult)
    cell = result.cells[0]
    assert isinstance(cell, MetricCell)
    assert cell.numerator_value == Decimal("6.00")
    assert cell.denominator_value == 2
    assert cell.value == Decimal("3.00")  # 6.00 / 2 verified outcomes


def test_result_carries_both_h7_fields() -> None:
    """The result's confidence carries minimum_tier + confidence_distribution (H7)."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.CANDIDATE)
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert isinstance(cell.confidence, RollupConfidence)
    assert cell.confidence.minimum_tier is BindingTier.CANDIDATE
    assert cell.confidence.confidence_distribution[BindingTier.EXACT] == 1
    assert cell.confidence.confidence_distribution[BindingTier.CANDIDATE] == 1


def test_retracted_excluded_and_reemitted() -> None:
    """A retracted outcome is excluded from the denominator and flagged for re-emit (H8)."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_RETRACTED, tier=BindingTier.EXACT)
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert cell.denominator_value == 1
    assert cell.retracted_excluded_count == 1
    assert result.requires_reemit is True


def test_no_reemit_when_nothing_retracted() -> None:
    """With no retractions the result does not request a re-emit."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    assert result.requires_reemit is False


def test_zero_denominator_yields_none_value() -> None:
    """A zero billing-grade denominator yields no ratio (never a divide-by-zero)."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    # only a candidate (advisory) outcome -> denominator 0
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.CANDIDATE)
    )
    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert cell.denominator_value == 0
    assert cell.value is None


def test_filter_excludes_nonmatching_cost() -> None:
    """A provider filter excludes cost events from other providers."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00", provider="anthropic"))
    costs.upsert(_TENANT, _cost("run-2", usd="9.00", provider="openai"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    plan = compile_plan_filtered_cost()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert cell.numerator_value == Decimal("6.00")  # openai cost excluded


def test_group_by_provider_yields_one_cell_per_provider() -> None:
    """A provider group_by produces one cell per distinct provider in the costs."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00", provider="anthropic"))
    costs.upsert(_TENANT, _cost("run-2", usd="9.00", provider="openai"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    plan = compile_plan_grouped_attempts()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    by_provider = {dict(cell.group_key)["provider"]: cell for cell in result.cells}
    assert set(by_provider) == {"anthropic", "openai"}
    assert by_provider["anthropic"].numerator_value == Decimal("1")
    assert by_provider["openai"].numerator_value == Decimal("1")


def test_attempt_count_numerator() -> None:
    """An attempt_count numerator counts cost events (one per attempt)."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    costs.upsert(_TENANT, _cost("run-2", usd="3.00"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    plan = compile_plan_attempts_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert cell.numerator_value == Decimal("2")
    assert cell.denominator_value == 1


def test_outcome_count_numerator_over_attempt_count_denominator() -> None:
    """outcome_count / attempt_count: confirmed outcomes over cost-event attempts."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    costs.upsert(_TENANT, _cost("run-2", usd="3.00"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    plan = compile_plan_outcomes_per_attempt()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert cell.numerator_value == Decimal("1")  # one confirmed outcome
    assert cell.denominator_value == 2  # two attempts
    assert cell.value == Decimal("0.50")


def test_cost_none_event_is_skipped_in_total() -> None:
    """A cost event with cost_usd=None (PTU/billing-uncertain) is skipped, not fabricated."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    none_cost = _cost("run-2", usd="0").model_copy(update={"cost_usd": None})
    costs.upsert(_TENANT, none_cost)
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )
    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert cell.numerator_value == Decimal("6.00")  # the None-cost event contributes nothing


def test_only_attempted_outcomes_yield_advisory_confidence() -> None:
    """With no bound outcomes the cell confidence is purely advisory (LIKELY)."""
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    outcomes.upsert(_TENANT, _outcome(signal_class=SignalClass.ACTION_ATTEMPTED, tier=None))
    plan = compile_plan_attempts_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))
    cell = result.cells[0]
    assert cell.confidence.minimum_tier is BindingTier.LIKELY
    assert cell.denominator_value == 0  # no confirmed outcome
    assert cell.value is None


def test_group_by_agent_resolves_cost_through_the_run_repo() -> None:
    """cost-by-agent: each cost event's run resolves to an agent; one cell per agent."""
    executor, costs, _outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-1", agent_name="researcher"))
    runs.upsert(_TENANT, _run("run-2", agent_name="writer"))
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    costs.upsert(_TENANT, _cost("run-2", usd="4.00"))

    plan = compile_plan_grouped_by_agent_cost()
    result = executor.run(_TENANT, plan, _WINDOW, ())

    by_agent = {dict(cell.group_key)["agent_name"]: cell for cell in result.cells}
    assert set(by_agent) == {"researcher", "writer"}
    assert by_agent["researcher"].numerator_value == Decimal("6.00")
    assert by_agent["writer"].numerator_value == Decimal("4.00")


def test_group_by_agent_buckets_unresolved_runs_under_unknown() -> None:
    """A cost event whose run has no agent (or no run row) falls into an 'unknown' bucket.

    The grouping is never silently dropped: a missing/agent-less run is surfaced as
    a distinct ``unknown`` agent cell rather than vanishing into an ungrouped total.
    """
    executor, costs, _outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-1", agent_name="researcher"))
    runs.upsert(_TENANT, _run("run-2", agent_name=None))  # a run with no agent
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    costs.upsert(_TENANT, _cost("run-2", usd="4.00"))
    costs.upsert(_TENANT, _cost("run-3", usd="1.00"))  # no run row at all

    plan = compile_plan_grouped_by_agent_cost()
    result = executor.run(_TENANT, plan, _WINDOW, ())

    by_agent = {dict(cell.group_key)["agent_name"]: cell for cell in result.cells}
    assert set(by_agent) == {"researcher", "unknown"}
    assert by_agent["researcher"].numerator_value == Decimal("6.00")
    # the agent-less run AND the run with no row both land in 'unknown' (4.00 + 1.00)
    assert by_agent["unknown"].numerator_value == Decimal("5.00")


def test_group_by_agent_without_a_run_repo_buckets_everything_under_unknown() -> None:
    """No run repo wired: agent-grouped cost all buckets under 'unknown', never dropped.

    The executor stays honest about an unresolvable join rather than silently
    collapsing the agent dimension into one ungrouped total.
    """
    costs = InMemoryCostEventRepository()
    outcomes = InMemoryOutcomeEventRepository()
    executor = MetricExecutor(cost_repo=costs, outcome_repo=outcomes)  # no run_repo
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    costs.upsert(_TENANT, _cost("run-2", usd="4.00"))

    plan = compile_plan_grouped_by_agent_cost()
    result = executor.run(_TENANT, plan, _WINDOW, ())

    by_agent = {dict(cell.group_key)["agent_name"]: cell for cell in result.cells}
    assert set(by_agent) == {"unknown"}
    assert by_agent["unknown"].numerator_value == Decimal("10.00")  # 6.00 + 4.00


def test_group_by_agent_ships_both_h7_fields_per_cell() -> None:
    """Each per-agent cost cell still carries the H7 confidence (minimum_tier + distribution)."""
    executor, costs, _outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-1", agent_name="researcher"))
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))

    plan = compile_plan_grouped_by_agent_cost()
    result = executor.run(_TENANT, plan, _WINDOW, ())
    cell = result.cells[0]
    assert isinstance(cell.confidence, RollupConfidence)
    assert cell.confidence.minimum_tier is BindingTier.LIKELY  # no bound outcome -> advisory
    assert cell.confidence.confidence_distribution[BindingTier.LIKELY] == 1


def test_group_by_tenant_yields_one_cell_for_the_scoped_tenant() -> None:
    """A tenant group_by is honoured (one cell): the query is already tenant-scoped."""
    executor, costs, _outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    costs.upsert(_TENANT, _cost("run-2", usd="4.00"))

    plan = compile_plan_grouped_by_tenant()
    result = executor.run(_TENANT, plan, _WINDOW, ())

    assert len(result.cells) == 1
    cell = result.cells[0]
    assert dict(cell.group_key)["tenant"] == str(_TENANT)
    assert cell.numerator_value == Decimal("10.00")


def test_every_grammar_dimension_is_handled_by_the_executor() -> None:
    """Ratchet (§5a): every grammar Dimension is honoured by the executor, none dropped.

    The grammar's allowlist and the executor's grouping must not drift: a dimension
    the DSL accepts but the executor ignores would silently mis-group (collapse into
    an ungrouped total). Adding a new ``Dimension`` without wiring it into the
    executor fails this guard.
    """
    from valuemaxx.metrics.executor import handled_dimensions
    from valuemaxx.metrics.grammar import Dimension

    assert set(Dimension) == handled_dimensions(), (
        "every grammar Dimension must be resolved by the executor (cost-keyed or "
        "outcome-keyed); a new dimension was added without wiring it in"
    )


# --- plan builders (kept here so each test reads independently) ---


def compile_plan_cost_per_outcome():
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="cost_per_outcome",
            numerator="total_cost_usd",
            denominator="verified_outcome_count",
            filters={},
            group_by=(),
        )
    )


def compile_plan_filtered_cost():
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="cost_per_outcome",
            numerator="total_cost_usd",
            denominator="verified_outcome_count",
            filters={"provider": "anthropic"},
            group_by=(),
        )
    )


def compile_plan_attempts_per_outcome():
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="attempts_per_outcome",
            numerator="attempt_count",
            denominator="outcome_count",
            filters={},
            group_by=(),
        )
    )


def compile_plan_grouped_attempts():
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="attempts_per_outcome",
            numerator="attempt_count",
            denominator="outcome_count",
            filters={},
            group_by=("provider",),
        )
    )


def compile_plan_outcomes_per_attempt():
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="outcomes_per_attempt",
            numerator="outcome_count",
            denominator="attempt_count",
            filters={},
            group_by=(),
        )
    )


def compile_plan_grouped_by_agent_cost():
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="cost_by_agent",
            numerator="total_cost_usd",
            denominator="verified_outcome_count",
            filters={},
            group_by=("agent_name",),
        )
    )


def compile_plan_grouped_by_tenant():
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="cost_by_tenant",
            numerator="total_cost_usd",
            denominator="verified_outcome_count",
            filters={},
            group_by=("tenant",),
        )
    )
