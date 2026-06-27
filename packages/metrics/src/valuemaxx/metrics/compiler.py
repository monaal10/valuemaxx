"""The pure metric compiler — MetricDefinition -> QueryPlan.

:func:`compile_plan` turns a validated :class:`~valuemaxx.core.MetricDefinition`
into a :class:`QueryPlan`: a typed, frozen, hashable description of the measures,
filters, group-by dimensions, and join strategy an executor will run against the
repository ABC.

The compiler is **PURE**: it performs no live store reads, no IO, no network, and
builds no SQL string. The same definition always compiles to an identical plan
(value-equal and hash-equal), which makes plans cacheable and testable without a
database. The plan names *allowlisted measures* (:class:`~valuemaxx.metrics.grammar.Measure`)
and a typed :class:`JoinStrategy`; it never carries free-text query fragments.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from valuemaxx.metrics.grammar import Measure, validate_definition

if TYPE_CHECKING:
    from valuemaxx.core import MetricDefinition


class JoinStrategy(StrEnum):
    """How the denominator's outcomes are joined to the run cost (the typed seam).

    ``billing_grade_outcomes`` joins only confirmed outcomes bound at an
    exact/deterministic tier (the honest cost-per-outcome denominator); excluding
    advisory and retracted outcomes is the executor's H8 job. ``all_outcomes``
    joins every outcome (for non-billing-grade ratios like attempts-per-outcome).
    """

    BILLING_GRADE_OUTCOMES = "billing_grade_outcomes"
    ALL_OUTCOMES = "all_outcomes"


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """A compiled, immutable plan for one metric (no SQL, no IO).

    Attributes:
        name: the metric name, echoed onto the result.
        numerator: the allowlisted numerator measure.
        denominator: the allowlisted denominator measure.
        filters: the (field, value) filters, as an immutable tuple of pairs so the
            plan is hashable and order-stable.
        group_by: the validated group-by dimensions, in declaration order.
        join_strategy: how the denominator outcomes are joined to the cost.
    """

    name: str
    numerator: Measure
    denominator: Measure
    filters: tuple[tuple[str, str], ...]
    group_by: tuple[str, ...]
    join_strategy: JoinStrategy


def _join_strategy_for(denominator: Measure) -> JoinStrategy:
    if denominator is Measure.VERIFIED_OUTCOME_COUNT:
        return JoinStrategy.BILLING_GRADE_OUTCOMES
    return JoinStrategy.ALL_OUTCOMES


def compile_plan(definition: MetricDefinition) -> QueryPlan:
    """Compile a validated ``definition`` into a pure :class:`QueryPlan`.

    Validates the definition against the closed allowlist first (raising
    :class:`~valuemaxx.metrics.errors.MetricGrammarError` on any non-allowlisted
    token), then builds the structural plan. The result is deterministic and
    side-effect-free: the same definition always yields an equal, hashable plan,
    and no store is ever touched.
    """
    validate_definition(definition)
    numerator = Measure(definition.numerator)
    denominator = Measure(definition.denominator)
    filters = tuple(sorted(definition.filters.items()))
    return QueryPlan(
        name=definition.name,
        numerator=numerator,
        denominator=denominator,
        filters=filters,
        group_by=tuple(definition.group_by),
        join_strategy=_join_strategy_for(denominator),
    )


__all__ = ["JoinStrategy", "QueryPlan", "compile_plan"]
