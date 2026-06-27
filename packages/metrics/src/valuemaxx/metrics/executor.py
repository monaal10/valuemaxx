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

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING

from valuemaxx.core import BindingTier, RollupConfidence, SignalClass
from valuemaxx.metrics.grammar import Dimension, Measure
from valuemaxx.metrics.propagation import denominator_outcomes
from valuemaxx.metrics.schemas import MetricCell, MetricResult

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Mapping, Sequence
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
    ) -> MetricResult:
        """Run ``plan`` over ``window`` for ``tenant_id``; return the metric result.

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

        cells: list[MetricCell] = []
        requires_reemit = False
        for key in group_keys:
            cell = self._build_cell(plan, key, events, outcomes, agent_by_run, tenant_value)
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
    ) -> MetricCell:
        cell_events = [
            e
            for e in events
            if _matches_key(_cost_group_key(e, plan.group_by, agent_by_run, tenant_value), key)
        ]
        cell_outcomes = [
            o for o in outcomes if _matches_key(_outcome_group_key(o, plan.group_by), key)
        ]
        numerator = _numerator_value(plan.numerator, cell_events, cell_outcomes)
        breakdown = denominator_outcomes(cell_outcomes)
        denominator = _denominator_value(plan.denominator, cell_events, cell_outcomes, breakdown)
        value = _ratio(numerator, denominator)
        confidence = _confidence(breakdown.tier_distribution)
        return MetricCell(
            group_key=key,
            numerator_value=numerator,
            denominator_value=denominator,
            value=value,
            confidence=confidence,
            advisory_excluded_count=breakdown.advisory_excluded_count,
            retracted_excluded_count=breakdown.retracted_excluded_count,
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


def _numerator_value(
    measure: Measure,
    events: Sequence[CostEvent],
    outcomes: Sequence[OutcomeEvent],
) -> Decimal:
    """Compute a numerator measure as a ``Decimal`` (a count is an integral Decimal)."""
    if measure is Measure.TOTAL_COST_USD:
        total = Decimal("0")
        for event in events:
            if event.cost_usd is not None:
                total += event.cost_usd
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
