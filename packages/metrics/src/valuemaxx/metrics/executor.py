"""The metric executor — run a compiled plan against injected repo ABCs.

:class:`MetricExecutor` reads cost events from the injected
:class:`~valuemaxx.core.CostEventRepository` over a :class:`MetricWindow`, applies
the plan's filters, groups by the plan's dimensions, and computes each cell's
numerator/denominator. The denominator honours the H8 honesty rules via
:func:`~valuemaxx.metrics.propagation.denominator_outcomes`: a billing-grade
denominator (``verified_outcome_count``) counts only confirmed outcomes bound at
an exact/deterministic tier; advisory and retracted outcomes are excluded but
counted, and any retraction sets ``requires_reemit`` so the metric is re-emitted
annotated rather than silently left (§3.1 H8).

The executor takes the candidate outcomes as an explicit sequence (the caller
fetches them within the tenant scope) — the core ``OutcomeEventRepository`` ABC is
keyed by id/binding, not by an arbitrary window, so passing the bound set keeps
the executor honest and store-agnostic.

Cost-by-agent grouping resolves each cost event's ``run_id`` to its
``Run.agent_name`` through the injected :class:`~valuemaxx.core.RunRepository` (a
``CostEvent`` carries no agent — the agent association lives on the ``Run``). A cost
event whose run is missing or whose run has no agent buckets under ``"unknown"`` so
the dimension is never silently dropped (the grouping is honest about what it could
not resolve rather than collapsing into one ungrouped total).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING

from valuemaxx.core import BindingTier, RollupConfidence, SignalClass
from valuemaxx.core.alias import EntityAlias, resolve_aliases
from valuemaxx.metrics.grammar import Dimension, Measure
from valuemaxx.metrics.propagation import (
    denominator_outcomes,
    is_billing_grade,
    propagate_causal_evidence,
)
from valuemaxx.metrics.schemas import MetricCell, MetricResult

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from datetime import datetime

    from valuemaxx.core import (
        CostEvent,
        CostEventRepository,
        OutcomeEvent,
        OutcomeEventRepository,
        RunId,
        RunRepository,
        TenantId,
    )
    from valuemaxx.metrics.compiler import QueryPlan
    from valuemaxx.metrics.propagation import DenominatorBreakdown

# The agent-dimension bucket for a cost event whose run is missing or carries no
# agent: the grouping surfaces what it could not resolve rather than dropping it.
_UNKNOWN_AGENT = "unknown"

# The dimensions resolved from a CostEvent (directly, or via the run join for
# agent_name) vs. from an OutcomeEvent. Every grammar Dimension MUST be handled by
# one side — :func:`handled_dimensions` exposes the union so the executor↔grammar
# parity guard test asserts no dimension the DSL accepts is silently dropped by the
# executor (ratchet §5a).
_COST_DIMENSIONS: frozenset[Dimension] = frozenset(
    {Dimension.PROVIDER, Dimension.MODEL, Dimension.AGENT_NAME, Dimension.TENANT}
)
_OUTCOME_DIMENSIONS: frozenset[Dimension] = frozenset({Dimension.OUTCOME_NAME})


def handled_dimensions() -> frozenset[Dimension]:
    """The grammar dimensions the executor resolves (cost-keyed or outcome-keyed).

    This is the executor's half of the executor↔grammar parity contract: it MUST
    equal the full set of grammar :class:`~valuemaxx.metrics.grammar.Dimension`
    members, so a dimension the DSL accepts can never be silently dropped (mis-
    grouped into an ungrouped total) by the executor (ratchet §5a). The conformance
    guard ``test_every_grammar_dimension_is_handled_by_the_executor`` asserts it.
    """
    return _COST_DIMENSIONS | _OUTCOME_DIMENSIONS


@dataclass(frozen=True, slots=True)
class MetricWindow:
    """The half-open time window ``[start, end)`` a metric aggregates over."""

    start: datetime
    end: datetime


def _cost_matches_filters(event: CostEvent, filters: tuple[tuple[str, str], ...]) -> bool:
    """True iff ``event`` matches every cost-keyed filter (unknown keys never match)."""
    for field, value in filters:
        if field == "provider" and event.provider != value:
            return False
        if field == "model" and event.model != value:
            return False
    return True


def _cost_group_key(
    event: CostEvent,
    group_by: tuple[str, ...],
    agent_by_run: Mapping[RunId, str],
    tenant_value: str,
) -> tuple[tuple[str, str], ...]:
    """The group key for a cost event over the plan's cost-keyed dimensions.

    ``agent_by_run`` maps a cost event's ``run_id`` to the agent it was resolved to
    (already defaulted to ``"unknown"`` for a missing/agent-less run), so the
    ``agent_name`` dimension is honoured without the executor importing the store.
    ``tenant_value`` is the scoped tenant id (every event shares it — the query is
    already tenant-scoped), so a ``tenant`` group_by yields one cell honestly rather
    than being silently dropped.
    """
    parts: list[tuple[str, str]] = []
    for dimension in group_by:
        if dimension == Dimension.PROVIDER:
            parts.append((dimension, event.provider))
        elif dimension == Dimension.MODEL:
            parts.append((dimension, event.model))
        elif dimension == Dimension.AGENT_NAME:
            parts.append((dimension, agent_by_run.get(event.run_id, _UNKNOWN_AGENT)))
        elif dimension == Dimension.TENANT:
            parts.append((dimension, tenant_value))
    return tuple(parts)


def _outcome_group_key(
    outcome: OutcomeEvent, group_by: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    """The group key for an outcome over the plan's outcome-keyed dimensions."""
    parts: list[tuple[str, str]] = []
    for dimension in group_by:
        if dimension == Dimension.OUTCOME_NAME:
            parts.append((dimension, outcome.name))
    return tuple(parts)


class MetricExecutor:
    """Runs a compiled :class:`~valuemaxx.metrics.compiler.QueryPlan`.

    Construct with the injected core repository ABCs; call :meth:`run` with a
    tenant scope, a plan, a window, and the candidate outcomes. The executor never
    imports ``valuemaxx.store`` — it depends only on the core ABCs (real Postgres
    wiring is G5, H6).
    """

    def __init__(
        self,
        *,
        cost_repo: CostEventRepository,
        outcome_repo: OutcomeEventRepository,
        run_repo: RunRepository | None = None,
    ) -> None:
        self._cost_repo = cost_repo
        self._outcome_repo = outcome_repo
        self._run_repo = run_repo

    def run(
        self,
        tenant_id: TenantId,
        plan: QueryPlan,
        window: MetricWindow,
        outcomes: Sequence[OutcomeEvent],
        aliases: Sequence[EntityAlias] = (),
    ) -> MetricResult:
        """Run ``plan`` over ``window`` for ``tenant_id``; return the metric result.

        ``aliases`` re-join traffic captured under a key the entity did not yet have
        (an anonymous session that later became a known lead). They are applied at
        query time rather than by rewriting stored spans, so a span keeps recording
        what the caller actually sent.

        Reads cost events from the injected repo within the window, applies the
        plan filters, partitions both costs and outcomes by the plan's group_by
        key, and builds one :class:`~valuemaxx.metrics.schemas.MetricCell` per
        group. Sets ``requires_reemit`` if any group excluded a retracted outcome.
        """
        events = [
            e
            for e in self._cost_repo.list_in_window(tenant_id, window.start, window.end)
            if _cost_matches_filters(e, plan.filters)
        ]
        agent_by_run = self._resolve_agents(tenant_id, plan, events)
        tenant_value = str(tenant_id)
        group_keys = self._group_keys(plan, events, outcomes, agent_by_run, tenant_value)

        share_by_run = _attribution_shares(plan, outcomes, self._run_repo, tenant_id, aliases)

        cells: list[MetricCell] = []
        requires_reemit = False
        for key in group_keys:
            cell = self._build_cell(
                plan,
                key,
                events,
                outcomes,
                agent_by_run,
                tenant_value,
                tenant_id,
                aliases,
                share_by_run,
            )
            if cell.retracted_excluded_count > 0:
                requires_reemit = True
            cells.append(cell)

        return MetricResult(
            name=plan.name,
            cells=tuple(cells),
            requires_reemit=requires_reemit,
        )

    def _resolve_agents(
        self, tenant_id: TenantId, plan: QueryPlan, events: Sequence[CostEvent]
    ) -> dict[RunId, str]:
        """Map each event's run to its agent name (``"unknown"`` if unresolvable).

        Only does the lookups when ``agent_name`` is grouped on (the common path
        groups by provider/model and needs no run join). Each distinct run is
        fetched once within the tenant scope; a missing run or a run with no
        ``agent_name`` defaults to ``"unknown"`` so the dimension is never dropped.
        """
        if Dimension.AGENT_NAME not in plan.group_by:
            return {}
        if self._run_repo is None:
            # No run repo wired: every event's agent is unresolvable, so they all
            # bucket under "unknown" rather than collapsing the grouping.
            return {}
        resolved: dict[RunId, str] = {}
        for run_id in {e.run_id for e in events}:
            run = self._run_repo.get(tenant_id, run_id)
            resolved[run_id] = (
                run.agent_name if run is not None and run.agent_name is not None else _UNKNOWN_AGENT
            )
        return resolved

    def _group_keys(
        self,
        plan: QueryPlan,
        events: Sequence[CostEvent],
        outcomes: Sequence[OutcomeEvent],
        agent_by_run: Mapping[RunId, str],
        tenant_value: str,
    ) -> list[tuple[tuple[str, str], ...]]:
        """The ordered, de-duplicated set of group keys present (empty key if ungrouped)."""
        if not plan.group_by:
            return [()]
        keys: list[tuple[tuple[str, str], ...]] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for event in events:
            key = _cost_group_key(event, plan.group_by, agent_by_run, tenant_value)
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
        for outcome in outcomes:
            key = _outcome_group_key(outcome, plan.group_by)
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
        return keys or [()]

    def _build_cell(
        self,
        plan: QueryPlan,
        key: tuple[tuple[str, str], ...],
        events: Sequence[CostEvent],
        outcomes: Sequence[OutcomeEvent],
        agent_by_run: Mapping[RunId, str],
        tenant_value: str,
        tenant_id: TenantId,
        aliases: Sequence[EntityAlias],
        share_by_run: Mapping[RunId, Decimal],
    ) -> MetricCell:
        cell_events = [
            e
            for e in events
            if _matches_key(_cost_group_key(e, plan.group_by, agent_by_run, tenant_value), key)
        ]
        cell_outcomes = [
            o for o in outcomes if _matches_key(_outcome_group_key(o, plan.group_by), key)
        ]
        numerator_events = _numerator_events(
            plan, cell_events, cell_outcomes, self._run_repo, tenant_id, aliases
        )
        numerator = _numerator_value(plan.numerator, numerator_events, cell_outcomes, share_by_run)
        breakdown = denominator_outcomes(cell_outcomes)
        denominator = _denominator_value(plan.denominator, cell_events, cell_outcomes, breakdown)
        value = _ratio(numerator, denominator)
        confidence = _confidence(breakdown.tier_distribution)
        causal = propagate_causal_evidence(o.binding.causal_evidence for o in cell_outcomes)
        return MetricCell(
            group_key=key,
            numerator_value=numerator,
            denominator_value=denominator,
            value=value,
            confidence=confidence,
            advisory_excluded_count=breakdown.advisory_excluded_count,
            retracted_excluded_count=breakdown.retracted_excluded_count,
            shared_attribution_count=sum(1 for e in numerator_events if e.run_id in share_by_run),
            causal_evidence=causal,
        )


def _matches_key(
    record_key: tuple[tuple[str, str], ...], cell_key: tuple[tuple[str, str], ...]
) -> bool:
    """True iff the record's (sub)key covers every pair in the cell key.

    An outcome key may be empty for a cost-dimension grouping (and vice versa); an
    empty record key matches any cell (the record contributes to every cell of the
    complementary dimension).
    """
    if not record_key:
        return True
    record = dict(record_key)
    return all(record.get(field) == value for field, value in cell_key if field in record)


def _numerator_events(
    plan: QueryPlan,
    events: Sequence[CostEvent],
    outcomes: Sequence[OutcomeEvent],
    run_repo: RunRepository | None,
    tenant_id: TenantId,
    aliases: Sequence[EntityAlias] = (),
) -> Sequence[CostEvent]:
    """Narrow the numerator to the runs that actually produced the denominator.

    Cost-per-outcome is a UNIT cost: the spend on the runs that succeeded, over the
    number that succeeded. Dividing the window's ENTIRE spend by the verified count
    is a portfolio ratio — it silently charges failed and in-flight runs to the
    successes, and it moves whenever traffic mix changes even if per-unit cost is
    flat. Only cost-over-verified-outcomes is affected: an attempt/outcome count
    numerator has no per-run cost to attribute.

    The narrowing needs run ids on both sides. When NO verified outcome carries one
    (an entity-bound or unbound outcome — advisory by construction), there is
    nothing to join on, so we return every event rather than an empty set: the
    honest degrade is the ratio the metric always reported, not a null that reads
    as "no data" when the real answer is "cannot attribute at this tier".
    """
    if plan.numerator is not Measure.TOTAL_COST_USD:
        return events
    if plan.denominator is not Measure.VERIFIED_OUTCOME_COUNT:
        return events

    counted = [
        outcome
        for outcome in outcomes
        if outcome.signal_class is SignalClass.OUTCOME_CONFIRMED
        and outcome.binding.tier is not None
        and is_billing_grade(outcome.binding.tier)
    ]
    producing_runs = {o.binding.run_id for o in counted if o.binding.run_id is not None}
    # An outcome that names only an ENTITY is the delayed-CRM shape: a meeting booked
    # days later carries `lead_id`, never the run id. Those runs ARE resolvable — they
    # carry the same entity key — so resolve them rather than falling back to the whole
    # window, which would charge every unrelated run to the successes.
    producing_runs |= _runs_for_entities(
        run_repo, tenant_id, (o for o in counted if o.binding.run_id is None), aliases
    )
    if not producing_runs:
        return events
    return [event for event in events if event.run_id in producing_runs]


def _attribution_shares(
    plan: QueryPlan,
    outcomes: Sequence[OutcomeEvent],
    run_repo: RunRepository | None,
    tenant_id: TenantId,
    aliases: Sequence[EntityAlias] = (),
) -> dict[RunId, Decimal]:
    """Each producing run's share of its own cost: 1/(outcomes it produced).

    A single run can produce several outcomes — one vibechk run both finalises an alt
    and completes an interview. Grouped by outcome_name each cell narrows to that
    outcome's producing runs, so without a share the run's FULL cost lands in every
    cell it touches and the columns sum to more than was actually spent. Summing past
    the provider invoice is the one error a buyer checks first, so split the run's
    cost evenly across the outcomes it produced; the columns then reconcile.

    Runs with a single outcome get share 1 and are unaffected.
    """
    if plan.numerator is not Measure.TOTAL_COST_USD:
        return {}
    if plan.denominator is not Measure.VERIFIED_OUTCOME_COUNT:
        return {}
    counts: Counter[RunId] = Counter()
    for outcome in outcomes:
        if outcome.signal_class is not SignalClass.OUTCOME_CONFIRMED:
            continue
        if outcome.binding.tier is None or not is_billing_grade(outcome.binding.tier):
            continue
        if outcome.binding.run_id is not None:
            counts[outcome.binding.run_id] += 1
            continue
        for run_id in _runs_for_entities(run_repo, tenant_id, [outcome], aliases):
            counts[run_id] += 1
    return {run_id: Decimal(1) / Decimal(n) for run_id, n in counts.items() if n > 1}


def _runs_for_entities(
    run_repo: RunRepository | None,
    tenant_id: TenantId,
    outcomes: Iterable[OutcomeEvent],
    aliases: Sequence[EntityAlias] = (),
) -> set[RunId]:
    """Run ids reachable from the entity keys of outcomes that carry no run id.

    Without a run repository there is nothing to resolve against, which is the
    pure-sequence test shape; the caller then degrades to the window total.
    """
    if run_repo is None:
        return set()
    resolved: set[RunId] = set()
    for outcome in outcomes:
        for entity_key in outcome.entity_keys:
            # An outcome names the entity as it is known NOW; the runs may have been
            # captured under an earlier key. Resolve the closure so the anonymous
            # half of the story is not orphaned.
            for key in resolve_aliases(entity_key, aliases):
                resolved.update(run.id for run in run_repo.list_by_entity(tenant_id, key))
    return resolved


def _numerator_value(
    measure: Measure,
    events: Sequence[CostEvent],
    outcomes: Sequence[OutcomeEvent],
    share_by_run: Mapping[RunId, Decimal] | None = None,
) -> Decimal:
    """Compute a numerator measure as a ``Decimal`` (a count is an integral Decimal)."""
    if measure is Measure.TOTAL_COST_USD:
        total = Decimal("0")
        for event in events:
            if event.cost_usd is not None:
                share = (
                    Decimal(1)
                    if share_by_run is None
                    else share_by_run.get(event.run_id, Decimal(1))
                )
                total += event.cost_usd * share
        return total
    if measure is Measure.ATTEMPT_COUNT:
        return Decimal(len(events))
    # Measure.OUTCOME_COUNT
    return Decimal(_confirmed_count(outcomes))


def _denominator_value(
    measure: Measure,
    events: Sequence[CostEvent],
    outcomes: Sequence[OutcomeEvent],
    breakdown: DenominatorBreakdown,
) -> int:
    """Compute a denominator measure as an integer count (H8 for verified)."""
    if measure is Measure.VERIFIED_OUTCOME_COUNT:
        return breakdown.verified_count
    if measure is Measure.OUTCOME_COUNT:
        return _confirmed_count(outcomes)
    # Measure.ATTEMPT_COUNT
    return len(events)


def _confirmed_count(outcomes: Sequence[OutcomeEvent]) -> int:
    """Count outcomes that are confirmed (retracted/attempted are not outcomes)."""
    return sum(1 for o in outcomes if o.signal_class is SignalClass.OUTCOME_CONFIRMED)


def _ratio(numerator: Decimal, denominator: int) -> Decimal | None:
    """``numerator / denominator`` (ROUND_HALF_EVEN), or None on a zero denominator."""
    if denominator == 0:
        return None
    return (numerator / Decimal(denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _confidence(tier_distribution: Counter[BindingTier]) -> RollupConfidence:
    """Build the H7 confidence from the tier distribution (empty -> a LIKELY advisory)."""
    tiers: list[BindingTier] = []
    for tier, count in tier_distribution.items():
        tiers.extend([tier] * count)
    if not tiers:
        # No bound outcomes contributed: the cell is purely advisory. Represent it
        # at the least-trusted tier so it can never read as billing-grade.
        return RollupConfidence(
            minimum_tier=BindingTier.LIKELY,
            confidence_distribution={BindingTier.LIKELY: 1},
        )
    return RollupConfidence.propagate(tiers)


__all__ = ["MetricExecutor", "MetricWindow", "handled_dimensions"]
