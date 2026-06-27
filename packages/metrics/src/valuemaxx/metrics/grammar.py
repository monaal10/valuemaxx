"""The metric grammar — a TYPED, closed-allowlist mini-DSL (no SQL, no ``eval``).

A user-defined metric is a small, fully-typed shape:

    filter  ->  outcome  ->  join strategy  ->  measure

expressed by the core :class:`~valuemaxx.core.MetricDefinition`. Every token a
definition can carry is a member of a *closed allowlist* declared in this module:

* the **measures** a numerator/denominator may name (``total_cost_usd``,
  ``attempt_count``, ``outcome_count``, ``verified_outcome_count`` ...);
* the **dimensions** a ``group_by`` may name (:class:`Dimension`);
* the **fields** a filter may key on (:data:`ALLOWED_FILTER_FIELDS`) and the
  shape a filter *value* may take (a plain scalar token — never SQL/eval).

:func:`validate_definition` checks a definition against these allowlists and the
cross-token rules (notably: a ``cost_per_outcome``-style numerator REQUIRES the
``verified_outcome_count`` denominator so candidate/likely/retracted outcomes can
never silently inflate the billing-grade denominator, §3.1 H8). It raises
:class:`~valuemaxx.metrics.errors.MetricGrammarError` on anything outside the
allowlist. Nothing here is ever passed to :func:`eval`/:func:`exec`; the DSL is a
membership check, not an interpreter (the ``no_eval_in_predicate`` rule).
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from valuemaxx.metrics.errors import MetricGrammarError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from valuemaxx.core import MetricDefinition


class Dimension(StrEnum):
    """The closed set of dimensions a metric may ``group_by`` (§11)."""

    PROVIDER = "provider"
    MODEL = "model"
    AGENT_NAME = "agent_name"
    OUTCOME_NAME = "outcome_name"
    TENANT = "tenant"


class Measure(StrEnum):
    """The closed set of measures a numerator/denominator may name.

    A measure is one of: a count (of attempts / of all outcomes / of
    *billing-grade verified* outcomes) or a sum-of-field (total cost). The
    ``verified_outcome_count`` measure is the only billing-grade denominator: it
    counts confirmed outcomes bound at an exact/deterministic tier, excluding
    candidate/likely (advisory) and retracted outcomes (§3.1 H8).
    """

    TOTAL_COST_USD = "total_cost_usd"
    ATTEMPT_COUNT = "attempt_count"
    OUTCOME_COUNT = "outcome_count"
    VERIFIED_OUTCOME_COUNT = "verified_outcome_count"


# The closed allowlists. ``frozenset`` makes them immutable closed sets — a token
# is valid iff it is a member, so the DSL can express nothing the allowlist does
# not already name (no free-text escape hatch).
NUMERATOR_TOKENS: Final[frozenset[str]] = frozenset(
    {Measure.TOTAL_COST_USD.value, Measure.ATTEMPT_COUNT.value, Measure.OUTCOME_COUNT.value}
)
DENOMINATOR_TOKENS: Final[frozenset[str]] = frozenset(
    {
        Measure.ATTEMPT_COUNT.value,
        Measure.OUTCOME_COUNT.value,
        Measure.VERIFIED_OUTCOME_COUNT.value,
    }
)
ALLOWED_FILTER_FIELDS: Final[frozenset[str]] = frozenset(
    {dimension.value for dimension in Dimension}
)
ALLOWED_DIMENSIONS: Final[frozenset[str]] = frozenset({dimension.value for dimension in Dimension})

# A cost-over-outcomes ratio (``total_cost_usd`` numerator) is the headline
# cost-per-outcome metric; it must use the billing-grade denominator so advisory
# (candidate/likely) and retracted outcomes never inflate it (§3.1 H8).
_COST_PER_OUTCOME_NUMERATOR: Final[str] = Measure.TOTAL_COST_USD.value
_REQUIRED_COST_DENOMINATOR: Final[str] = Measure.VERIFIED_OUTCOME_COUNT.value

# A filter value is a plain scalar token: alphanumerics, dot, dash, underscore,
# colon, slash, space. Anything else (quotes, semicolons, parentheses, SQL
# punctuation, dynamic-execution words) is rejected — there is no string
# interpolation into a query, so a value never needs richer characters. The
# markers below are deliberately written WITHOUT a trailing ``(`` so the rejecting
# code itself contains no dynamic-execution call substring (the source stays clean
# for the no_eval_in_predicate scan); the ``(`` marker already subsumes any call.
_FILTER_VALUE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9 ._:/\-]+$")
_FORBIDDEN_MARKERS: Final[tuple[str, ...]] = (
    "eval",
    "exec",
    "__",
    ";",
    "--",
    "'",
    '"',
    "(",
    ")",
    "/*",
)


def _reject_free_text(token: str, *, where: str) -> None:
    """Raise if ``token`` carries an SQL/eval marker (defence in depth over the regex)."""
    lowered = token.lower()
    for marker in _FORBIDDEN_MARKERS:
        if marker in lowered:
            raise MetricGrammarError(
                f"{where} {token!r} contains a forbidden construct {marker!r}; "
                "the metric DSL is a closed allowlist with no free-text SQL or eval"
            )


def _validate_numerator(numerator: str) -> None:
    _reject_free_text(numerator, where="numerator")
    if numerator not in NUMERATOR_TOKENS:
        raise MetricGrammarError(
            f"numerator {numerator!r} is not an allowed measure; "
            f"choose one of {sorted(NUMERATOR_TOKENS)}"
        )


def _validate_denominator(denominator: str) -> None:
    _reject_free_text(denominator, where="denominator")
    if denominator not in DENOMINATOR_TOKENS:
        raise MetricGrammarError(
            f"denominator {denominator!r} is not an allowed measure; "
            f"choose one of {sorted(DENOMINATOR_TOKENS)}"
        )


def _validate_cost_per_outcome(numerator: str, denominator: str) -> None:
    if numerator == _COST_PER_OUTCOME_NUMERATOR and denominator != _REQUIRED_COST_DENOMINATOR:
        raise MetricGrammarError(
            f"a {numerator!r} (cost-per-outcome) metric REQUIRES "
            f"denominator={_REQUIRED_COST_DENOMINATOR!r} so advisory and retracted "
            "outcomes never inflate the billing-grade denominator (§3.1 H8); "
            f"got denominator={denominator!r}"
        )


def _validate_filters(filters: Mapping[str, str]) -> None:
    for field, value in filters.items():
        if field not in ALLOWED_FILTER_FIELDS:
            raise MetricGrammarError(
                f"filter field {field!r} is not allowed; "
                f"choose one of {sorted(ALLOWED_FILTER_FIELDS)}"
            )
        if not _FILTER_VALUE_RE.match(value):
            raise MetricGrammarError(
                f"filter value {value!r} for field {field!r} is not a plain scalar token; "
                "the metric DSL forbids free-text SQL/punctuation in filter values"
            )
        _reject_free_text(value, where="filter value")


def _validate_group_by(group_by: tuple[str, ...]) -> None:
    for dimension in group_by:
        _reject_free_text(dimension, where="group_by dimension")
        if dimension not in ALLOWED_DIMENSIONS:
            raise MetricGrammarError(
                f"group_by dimension {dimension!r} is not allowed; "
                f"choose one of {sorted(ALLOWED_DIMENSIONS)}"
            )


def validate_definition(definition: MetricDefinition) -> MetricDefinition:
    """Validate ``definition`` against the closed allowlist DSL; return it unchanged.

    Raises :class:`~valuemaxx.metrics.errors.MetricGrammarError` if any token (the
    numerator/denominator measure, a ``group_by`` dimension, or a filter
    field/value) falls outside the allowlist, if a filter value carries free-text
    SQL/eval, or if a ``cost_per_outcome`` numerator is paired with anything but
    the ``verified_outcome_count`` denominator. The returned object is the same
    instance (validation is side-effect-free), so callers can chain
    ``compile_plan(validate_definition(d))``.
    """
    _validate_numerator(definition.numerator)
    _validate_denominator(definition.denominator)
    _validate_cost_per_outcome(definition.numerator, definition.denominator)
    _validate_filters(definition.filters)
    _validate_group_by(definition.group_by)
    return definition


__all__ = [
    "ALLOWED_DIMENSIONS",
    "ALLOWED_FILTER_FIELDS",
    "DENOMINATOR_TOKENS",
    "NUMERATOR_TOKENS",
    "Dimension",
    "Measure",
    "validate_definition",
]
