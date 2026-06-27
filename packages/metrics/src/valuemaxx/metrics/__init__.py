"""valuemaxx.metrics — the user-defined metric engine (§11).

A metric is a TYPED, closed-allowlist mini-DSL — ``filter -> outcome -> join
strategy -> measure`` (count / sum-of-field / ratio) over a core
:class:`~valuemaxx.core.MetricDefinition`. There is no free-text SQL and no
``eval``/``exec``: :func:`~valuemaxx.metrics.grammar.validate_definition` rejects
anything outside the allowlist (the ``no_eval_in_predicate`` rule).

:func:`~valuemaxx.metrics.compiler.compile_plan` turns a definition into a PURE,
immutable :class:`~valuemaxx.metrics.compiler.QueryPlan` (no live store reads).
:class:`~valuemaxx.metrics.executor.MetricExecutor` runs the plan against the
injected core repository ABCs, propagating confidence conservatively (aggregation
never raises confidence; the rollup carries both H7 fields) and excluding
candidate/likely and retracted outcomes from the billing-grade denominator while
still counting them — a retraction re-emits the annotated metric, never silently
left (§3.1 H7/H8).

Depends only on ``valuemaxx.core`` ABCs/Protocols and ``valuemaxx.capabilities``;
it never imports a sibling logic package or ``valuemaxx.store``.
"""

from __future__ import annotations

from valuemaxx.metrics.capabilities import (
    MetricRuntime,
    MetricsNotWiredError,
    bind_runtime,
    register,
)
from valuemaxx.metrics.compiler import JoinStrategy, QueryPlan, compile_plan
from valuemaxx.metrics.errors import MetricError, MetricGrammarError
from valuemaxx.metrics.executor import MetricExecutor, MetricWindow
from valuemaxx.metrics.grammar import (
    Dimension,
    Measure,
    validate_definition,
)
from valuemaxx.metrics.propagation import (
    DenominatorBreakdown,
    denominator_outcomes,
    is_billing_grade,
    propagate,
)
from valuemaxx.metrics.schemas import MetricCell, MetricResult

__all__ = [
    "DenominatorBreakdown",
    "Dimension",
    "JoinStrategy",
    "Measure",
    "MetricCell",
    "MetricError",
    "MetricExecutor",
    "MetricGrammarError",
    "MetricResult",
    "MetricRuntime",
    "MetricWindow",
    "MetricsNotWiredError",
    "QueryPlan",
    "bind_runtime",
    "compile_plan",
    "denominator_outcomes",
    "is_billing_grade",
    "propagate",
    "register",
    "validate_definition",
]
