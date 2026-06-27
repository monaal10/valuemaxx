"""Compiler tests — MetricDefinition -> QueryPlan must be PURE.

The compiler builds a typed, structural query plan against the repository ABC. It
performs NO live store reads, NO IO, and NO SQL-string construction: the same
definition always compiles to an identical plan. The plan is a frozen, hashable
dataclass describing measures/filters/group_by/join strategy — never a SQL string.
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError

import pytest
from valuemaxx.core import MetricDefinition
from valuemaxx.metrics.compiler import (
    JoinStrategy,
    QueryPlan,
    compile_plan,
)
from valuemaxx.metrics.errors import MetricGrammarError
from valuemaxx.metrics.grammar import Measure


def _definition(
    *,
    numerator: str = "total_cost_usd",
    denominator: str = "verified_outcome_count",
    filters: dict[str, str] | None = None,
    group_by: tuple[str, ...] = (),
) -> MetricDefinition:
    return MetricDefinition(
        name="cost_per_outcome",
        numerator=numerator,
        denominator=denominator,
        filters=filters or {},
        group_by=group_by,
    )


def test_compiles_to_a_query_plan() -> None:
    """A valid definition compiles to a QueryPlan naming both measures."""
    plan = compile_plan(_definition(filters={"provider": "anthropic"}, group_by=("model",)))
    assert isinstance(plan, QueryPlan)
    assert plan.numerator is Measure.TOTAL_COST_USD
    assert plan.denominator is Measure.VERIFIED_OUTCOME_COUNT


def test_plan_carries_filters_and_group_by() -> None:
    """The plan carries the validated filters and group_by as immutable tuples."""
    plan = compile_plan(
        _definition(filters={"provider": "anthropic", "model": "opus"}, group_by=("model",))
    )
    assert dict(plan.filters) == {"provider": "anthropic", "model": "opus"}
    assert plan.group_by == ("model",)


def test_cost_metric_uses_billing_grade_join_strategy() -> None:
    """A cost-per-outcome plan joins on the billing-grade denominator strategy."""
    plan = compile_plan(_definition())
    assert plan.join_strategy is JoinStrategy.BILLING_GRADE_OUTCOMES


def test_non_cost_metric_uses_all_outcomes_join_strategy() -> None:
    """A non-billing-grade denominator joins on all outcomes."""
    plan = compile_plan(_definition(numerator="attempt_count", denominator="outcome_count"))
    assert plan.join_strategy is JoinStrategy.ALL_OUTCOMES


def test_compile_is_deterministic() -> None:
    """Same input -> identical plan (the plan is value-equal and hashable)."""
    definition = _definition(filters={"provider": "anthropic"}, group_by=("model",))
    first = compile_plan(definition)
    second = compile_plan(definition)
    assert first == second
    assert hash(first) == hash(second)


def test_plan_is_frozen() -> None:
    """The plan is immutable — a compiled plan can never be mutated in place."""
    plan = compile_plan(_definition())
    with pytest.raises(FrozenInstanceError):
        plan.numerator = Measure.ATTEMPT_COUNT  # type: ignore[misc]


def test_compile_validates_before_planning() -> None:
    """compile_plan rejects an invalid definition (it validates first)."""
    with pytest.raises(MetricGrammarError):
        compile_plan(_definition(numerator="DROP TABLE"))


def test_compile_does_not_emit_sql_strings() -> None:
    """Purity: no field on the plan is a raw SQL string (no free-text query)."""
    plan = compile_plan(_definition(filters={"provider": "anthropic"}))
    banned = ("select", "from", "where", "join", ";", "--")
    for value in (plan.numerator.value, plan.denominator.value, plan.join_strategy.value):
        lowered = value.lower()
        assert not any(token in lowered for token in banned)


def test_compile_source_imports_no_io_modules() -> None:
    """Purity: the compiler module imports no IO/DB/network modules.

    A pure compiler must not be able to touch a live store; assert at the source
    level that it imports nothing capable of IO.
    """
    from valuemaxx.metrics import compiler

    source = inspect.getsource(compiler)
    forbidden = (
        "import sqlite3",
        "import psycopg",
        "import sqlalchemy",
        "import requests",
        "import socket",
        "open(",
    )
    assert not any(token in source for token in forbidden)
