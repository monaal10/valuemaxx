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
from valuemaxx.core.alias import EntityAlias
from valuemaxx.metrics.compiler import compile_plan
from valuemaxx.metrics.executor import MetricExecutor, MetricWindow
from valuemaxx.metrics.grammar import Dimension
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


def _outcome(
    *,
    signal_class: SignalClass,
    tier: BindingTier | None,
    run: str | None = None,
    entity_keys: frozenset[tuple[str, str]] = frozenset(),
    name: str = "outcome",
) -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=_TENANT,
        id=OutcomeEventId(f"oe-{uuid4()}"),
        name=name,
        signal_class=signal_class,
        value=Decimal("1"),
        occurred_at=datetime(2026, 6, 15, tzinfo=UTC),
        binding=OutcomeBinding(
            run_id=RunId(run) if run else None, tier=tier, bound_by="t1" if tier else None
        ),
        entity_keys=entity_keys,
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


def test_cost_per_outcome_counts_only_the_runs_that_produced_an_outcome() -> None:
    """A run with no verified outcome must not inflate the numerator.

    This is the difference between a UNIT cost and a portfolio ratio. Summing every
    cost event in the window and dividing by the outcomes that happened answers
    "what did we spend per success across everything we tried" — which reads as
    cost-per-outcome on a dashboard but silently charges failed and in-flight runs
    to the successes. Here run-2 produced nothing, so only run-1's $6 is a unit
    cost; including run-2 would report $16.
    """
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    costs.upsert(_TENANT, _cost("run-2", usd="10.00"))  # no outcome — a failure or in-flight
    outcomes.upsert(
        _TENANT,
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT, run="run-1"),
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    cell = result.cells[0]
    assert cell.denominator_value == 1
    assert cell.numerator_value == Decimal("6.00")
    assert cell.value == Decimal("6.00")


def test_unbound_outcomes_do_not_strand_the_whole_numerator() -> None:
    """When NO outcome carries a run id, fall back to the window total.

    An unbound outcome is advisory and already excluded from the billing-grade
    denominator, so filtering the numerator to "runs that produced one" would leave
    zero cost over zero outcomes and report nothing at all. The honest degrade is
    the portfolio ratio the metric always used, not a silent null.
    """
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    outcomes.upsert(
        _TENANT, _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT)
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    cell = result.cells[0]
    assert cell.numerator_value == Decimal("6.00")


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


def compile_plan_cost_per_outcome(group_by: list[Dimension] | None = None):
    from valuemaxx.core import MetricDefinition

    return compile_plan(
        MetricDefinition(
            name="cost_per_outcome",
            numerator="total_cost_usd",
            denominator="verified_outcome_count",
            filters={},
            group_by=tuple(d.value for d in (group_by or [])),
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


def test_entity_bound_outcome_narrows_cost_to_that_entitys_runs() -> None:
    """An outcome that names only an ENTITY still gets a unit cost, not portfolio spend.

    This is the delayed-CRM shape and the reason the product exists: a meeting is
    booked days later carrying `lead_id`, never the run id. Until now the numerator
    could only narrow when the outcome carried a run id, so this case silently fell
    back to ALL cost in the window — "cost per meeting" became total spend divided by
    meetings, charging every unrelated run to the successes.

    The runs are resolvable: they carry the same entity key, and the executor already
    holds a RunRepository that can list by it.
    """
    executor, costs, outcomes, runs = _executor()
    lead = ("lead_id", "8172")
    runs.upsert(_TENANT, _run("run-lead", agent_name="sdr"))
    runs.upsert(_TENANT, _run("run-other", agent_name="sdr"))
    # Only run-lead touched this lead.
    runs.upsert(
        _TENANT,
        Run(
            tenant_id=_TENANT,
            id=RunId("run-lead"),
            agent_name="sdr",
            started_at=datetime(2026, 6, 15, tzinfo=UTC),
            ended_at=None,
            entity_keys=frozenset({lead}),
        ),
    )
    costs.upsert(_TENANT, _cost("run-lead", usd="3.00"))
    costs.upsert(_TENANT, _cost("run-other", usd="97.00"))  # unrelated traffic
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            entity_keys=frozenset({lead}),
        ),
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    cell = result.cells[0]
    assert cell.denominator_value == 1
    # $3.00, not $100.00.
    assert cell.numerator_value == Decimal("3.00")


def test_unresolvable_outcome_still_reports_the_window_total() -> None:
    """With neither a run id nor a resolvable entity there is nothing to join on.

    Returning an empty numerator would read as "no spend" — a confident zero. The
    honest degrade is the portfolio ratio the metric always reported.
    """
    executor, costs, outcomes, _runs = _executor()
    costs.upsert(_TENANT, _cost("run-1", usd="6.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT),
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    assert result.cells[0].numerator_value == Decimal("6.00")


def test_a_run_serving_two_outcome_names_splits_its_cost_between_them() -> None:
    """Grouped by outcome_name, a shared run must not be charged in full to each cell.

    One vibechk run both finalises an alt and completes an interview. Charging its
    whole $10 to `alt_created` AND its whole $10 to `interview_taken` reports $20 of
    spend from $10 of tokens — summing the columns of the dashboard exceeds the
    provider invoice, which is the fastest way for a buyer to stop trusting every
    other number on the page.

    The honest split is per-outcome share: $5 each.
    """
    executor, costs, outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-shared", agent_name="builder"))
    costs.upsert(_TENANT, _cost("run-shared", usd="10.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.EXACT,
            run="run-shared",
            name="alt_created",
        ),
    )
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.EXACT,
            run="run-shared",
            name="interview_taken",
        ),
    )

    plan = compile_plan_cost_per_outcome(group_by=[Dimension.OUTCOME_NAME])
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    by_name = {dict(c.group_key)["outcome_name"]: c for c in result.cells}
    assert by_name["alt_created"].numerator_value == Decimal("5.00")
    assert by_name["interview_taken"].numerator_value == Decimal("5.00")
    # The whole point: the columns sum back to what was actually spent.
    assert sum(c.numerator_value for c in result.cells) == Decimal("10.00")


def test_cell_reports_its_causal_evidence() -> None:
    """The axis has to reach the cell, or nothing can render it beside the number."""
    from valuemaxx.core import CausalEvidence

    executor, costs, outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-1", agent_name="a"))
    costs.upsert(_TENANT, _cost("run-1", usd="1.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT, run="run-1"),
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    assert result.cells[0].causal_evidence is CausalEvidence.OBSERVATIONAL


def test_a_shared_run_is_flagged_as_overlapping_not_silently_divided() -> None:
    """A run producing two outcomes splits its cost — and SAYS that it did.

    The split itself is right: without it the run's full cost lands in both cells and
    the columns sum past the provider invoice. But a divided number that looks like a
    measured one is the dishonesty the honesty axes exist to prevent — a buyer reading
    "$2.50 per alt" deserves to know it is half of a run shared with an interview.
    """
    executor, costs, outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-shared", agent_name="builder"))
    costs.upsert(_TENANT, _cost("run-shared", usd="5.00"))
    for name in ("alt_created", "interview_taken"):
        outcomes.upsert(
            _TENANT,
            _outcome(
                signal_class=SignalClass.OUTCOME_CONFIRMED,
                tier=BindingTier.EXACT,
                run="run-shared",
                name=name,
            ),
        )

    plan = compile_plan_cost_per_outcome(group_by=[Dimension.OUTCOME_NAME])
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    assert len(result.cells) == 2
    for cell in result.cells:
        # Half of $5.00 — the columns reconcile against the invoice.
        assert cell.numerator_value == Decimal("2.50")
        # ...and the cell admits the number is a split, not a measurement.
        assert cell.shared_attribution_count == 1

    unshared = compile_plan_cost_per_outcome()
    solo = executor.run(_TENANT, unshared, _WINDOW, outcomes.list_all(_TENANT))
    assert solo.cells[0].shared_attribution_count == 1


def test_an_alias_re_joins_cost_spent_under_an_anonymous_key() -> None:
    """The A4 payoff: traffic captured before the entity was known still costs out.

    A session spends real money answering questions while anonymous. It becomes a
    known lead later, and the outcome — booked days after — names only the lead. With
    no alias the anonymous spend is orphaned: the run is invisible to the entity
    lookup, so the numerator falls back to the window total. The alias makes the two
    keys one entity at QUERY time, without rewriting the span that recorded what the
    caller actually sent.
    """
    executor, costs, outcomes, runs = _executor()
    session = ("session_id", "abc")
    lead = ("lead_id", "8172")
    runs.upsert(
        _TENANT,
        Run(
            tenant_id=_TENANT,
            id=RunId("run-anon"),
            agent_name="sdr",
            started_at=datetime(2026, 6, 15, tzinfo=UTC),
            ended_at=None,
            entity_keys=frozenset({session}),
        ),
    )
    runs.upsert(_TENANT, _run("run-unrelated", agent_name="sdr"))
    costs.upsert(_TENANT, _cost("run-anon", usd="4.00"))
    costs.upsert(_TENANT, _cost("run-unrelated", usd="96.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            entity_keys=frozenset({lead}),
        ),
    )

    plan = compile_plan_cost_per_outcome()
    aliases = [EntityAlias(source=session, target=lead)]
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT), aliases=aliases)

    # $4.00 — the anonymous session's spend — not $100.00.
    assert result.cells[0].numerator_value == Decimal("4.00")


def test_without_an_alias_the_anonymous_spend_stays_unjoined() -> None:
    """The same shape with no alias must NOT silently claim the join."""
    executor, costs, outcomes, runs = _executor()
    runs.upsert(
        _TENANT,
        Run(
            tenant_id=_TENANT,
            id=RunId("run-anon"),
            agent_name="sdr",
            started_at=datetime(2026, 6, 15, tzinfo=UTC),
            ended_at=None,
            entity_keys=frozenset({("session_id", "abc")}),
        ),
    )
    costs.upsert(_TENANT, _cost("run-anon", usd="4.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            entity_keys=frozenset({("lead_id", "8172")}),
        ),
    )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    # Nothing resolved, so the honest degrade is the window total — never a
    # confident join we did not earn.
    assert result.cells[0].numerator_value == Decimal("4.00")


def test_a_shared_run_is_not_halved_when_both_outcomes_land_in_one_cell() -> None:
    """The split prevents double-counting ACROSS cells; within one cell there is none.

    Splitting a shared run's cost exists so that grouping by outcome_name does not
    charge the same $5.00 to both the alt_created and interview_taken columns —
    together they would sum past the provider invoice. An UNGROUPED metric puts both
    outcomes in a single cell, where the run's cost appears exactly once, so applying
    the share there under-reports real spend by half: $2.50 of a $5.00 invoice simply
    vanishes.

    Under-reporting is the more dangerous direction. Summing past the invoice is
    caught immediately by a buyer reconciling against their provider bill; summing
    UNDER it looks like good news and is believed.
    """
    executor, costs, outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-shared", agent_name="builder"))
    costs.upsert(_TENANT, _cost("run-shared", usd="5.00"))
    for name in ("alt_created", "interview_taken"):
        outcomes.upsert(
            _TENANT,
            _outcome(
                signal_class=SignalClass.OUTCOME_CONFIRMED,
                tier=BindingTier.EXACT,
                run="run-shared",
                name=name,
            ),
        )

    plan = compile_plan_cost_per_outcome()
    result = executor.run(_TENANT, plan, _WINDOW, outcomes.list_all(_TENANT))

    cell = result.cells[0]
    assert cell.denominator_value == 2
    # The whole invoice, counted once.
    assert cell.numerator_value == Decimal("5.00")
    # Still flagged: the per-outcome figure below is a shared run's cost.
    assert cell.shared_attribution_count == 1


# --- adversarial audit (Phase C) --------------------------------------------
# Each of these is an attempt to make the metric state something untrue. Per the
# repo's ratchet rule every dishonesty class found becomes a permanent guard, so
# these stay as tests rather than as a one-off audit report.


def test_a_caller_cannot_promote_its_own_outcome_into_the_denominator() -> None:
    """A candidate-tier outcome must never count, however it is labelled.

    The whole billing-grade distinction collapses if a caller can assert its way in:
    cost per outcome would silently include guesses, and the number would drop
    exactly when attribution got WEAKER — the most flattering possible lie.
    """
    executor, costs, outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-1", agent_name="bot"))
    costs.upsert(_TENANT, _cost("run-1", usd="9.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.CANDIDATE,
            run="run-1",
        ),
    )

    result = executor.run(
        _TENANT, compile_plan_cost_per_outcome(), _WINDOW, outcomes.list_all(_TENANT)
    )

    cell = result.cells[0]
    assert cell.denominator_value == 0
    # No denominator means NO ratio — never a fabricated one.
    assert cell.value is None
    assert cell.advisory_excluded_count == 1


def test_a_retracted_outcome_cannot_keep_inflating_the_denominator() -> None:
    """A refunded deal must leave the denominator, and say the metric needs re-emitting.

    Otherwise every retraction permanently improves the reported unit cost: the spend
    stays, the outcome silently stays counted, and cost-per-outcome looks better the
    more customers churn.
    """
    executor, costs, outcomes, runs = _executor()
    runs.upsert(_TENANT, _run("run-1", agent_name="bot"))
    costs.upsert(_TENANT, _cost("run-1", usd="4.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_RETRACTED,
            tier=BindingTier.EXACT,
            run="run-1",
        ),
    )

    result = executor.run(
        _TENANT, compile_plan_cost_per_outcome(), _WINDOW, outcomes.list_all(_TENANT)
    )

    assert result.cells[0].denominator_value == 0
    assert result.cells[0].retracted_excluded_count == 1
    assert result.requires_reemit is True


def test_an_alias_cannot_merge_two_different_entities_spend() -> None:
    """Aliasing must not become a way to pull unrelated cost into a unit.

    The closure is the one place where a caller-supplied claim widens what counts as
    "this entity's spend". If an unrelated key resolved through it, a customer could
    make any outcome look arbitrarily cheap by asserting enough aliases.
    """
    executor, costs, outcomes, runs = _executor()
    lead, stranger = ("lead_id", "8172"), ("lead_id", "9999")
    for run_id, key, usd in (("run-lead", lead, "2.00"), ("run-stranger", stranger, "98.00")):
        runs.upsert(
            _TENANT,
            Run(
                tenant_id=_TENANT,
                id=RunId(run_id),
                agent_name="sdr",
                started_at=datetime(2026, 6, 15, tzinfo=UTC),
                ended_at=None,
                entity_keys=frozenset({key}),
            ),
        )
        costs.upsert(_TENANT, _cost(run_id, usd=usd))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            entity_keys=frozenset({lead}),
        ),
    )

    # An alias between two OTHER keys must not drag the stranger's run in.
    unrelated = [EntityAlias(source=("session_id", "s1"), target=("session_id", "s2"))]
    result = executor.run(
        _TENANT,
        compile_plan_cost_per_outcome(),
        _WINDOW,
        outcomes.list_all(_TENANT),
        aliases=unrelated,
    )

    assert result.cells[0].numerator_value == Decimal("2.00")


def test_an_alias_cycle_cannot_hang_or_inflate_a_metric() -> None:
    """Mutually-asserted aliases must terminate and must not multiply the join.

    The closure walk is the one unbounded loop in the query path, and it walks
    caller-supplied data. A cycle that hung would take the dashboard down; a cycle
    that re-counted a run per traversal would inflate the numerator without any
    invalid input ever being rejected.
    """
    executor, costs, outcomes, runs = _executor()
    a, b = ("session_id", "a"), ("lead_id", "b")
    runs.upsert(
        _TENANT,
        Run(
            tenant_id=_TENANT,
            id=RunId("run-a"),
            agent_name="sdr",
            started_at=datetime(2026, 6, 15, tzinfo=UTC),
            ended_at=None,
            entity_keys=frozenset({a}),
        ),
    )
    costs.upsert(_TENANT, _cost("run-a", usd="7.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            entity_keys=frozenset({b}),
        ),
    )

    cyclic = [
        EntityAlias(source=a, target=b),
        EntityAlias(source=b, target=a),
        EntityAlias(source=a, target=b),  # asserted twice for good measure
    ]
    result = executor.run(
        _TENANT,
        compile_plan_cost_per_outcome(),
        _WINDOW,
        outcomes.list_all(_TENANT),
        aliases=cyclic,
    )

    # Counted ONCE despite three edges and a cycle.
    assert result.cells[0].numerator_value == Decimal("7.00")


def test_an_entity_resolving_to_many_runs_counts_each_run_once() -> None:
    """Several runs working one lead sum once each — never once per outcome key.

    The entity path resolves runs per outcome; a naive implementation that appended
    instead of unioning would count a run again for every entity key an outcome
    carries, quietly multiplying the numerator by the width of the key set.
    """
    executor, costs, outcomes, runs = _executor()
    lead, email = ("lead_id", "8172"), ("email", "a@b.c")
    for run_id in ("run-1", "run-2"):
        runs.upsert(
            _TENANT,
            Run(
                tenant_id=_TENANT,
                id=RunId(run_id),
                agent_name="sdr",
                started_at=datetime(2026, 6, 15, tzinfo=UTC),
                ended_at=None,
                entity_keys=frozenset({lead, email}),
            ),
        )
        costs.upsert(_TENANT, _cost(run_id, usd="1.50"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            entity_keys=frozenset({lead, email}),
        ),
    )

    result = executor.run(
        _TENANT, compile_plan_cost_per_outcome(), _WINDOW, outcomes.list_all(_TENANT)
    )

    # $3.00 total, not $6.00 (two runs x two matching keys).
    assert result.cells[0].numerator_value == Decimal("3.00")


def test_another_tenants_runs_are_never_reachable_through_an_entity() -> None:
    """Entity resolution must not cross the tenant boundary.

    Entity keys are caller-chosen strings, so two customers can easily both use
    `lead_id=1`. If the entity path reached across tenants, one customer's outcome
    would attribute another customer's spend — a cost error and a data leak in the
    same query.
    """
    executor, costs, outcomes, runs = _executor()
    other = TenantId(uuid4())
    lead = ("lead_id", "1")
    for tenant, run_id in ((_TENANT, "mine"), (other, "theirs")):
        runs.upsert(
            tenant,
            Run(
                tenant_id=tenant,
                id=RunId(run_id),
                agent_name="sdr",
                started_at=datetime(2026, 6, 15, tzinfo=UTC),
                ended_at=None,
                entity_keys=frozenset({lead}),
            ),
        )
    costs.upsert(_TENANT, _cost("mine", usd="2.00"))
    outcomes.upsert(
        _TENANT,
        _outcome(
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            tier=BindingTier.DETERMINISTIC,
            entity_keys=frozenset({lead}),
        ),
    )

    result = executor.run(
        _TENANT, compile_plan_cost_per_outcome(), _WINDOW, outcomes.list_all(_TENANT)
    )

    assert result.cells[0].numerator_value == Decimal("2.00")
