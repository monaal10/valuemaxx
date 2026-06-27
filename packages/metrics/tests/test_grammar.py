"""Grammar (closed-allowlist mini-DSL) tests for valuemaxx.metrics.

The metric grammar is a TYPED allowlist: a metric is filter -> outcome -> join
strategy -> measure (count / sum-of-field / ratio). There is no free-text SQL and
no ``eval``/``exec``. ``validate_definition`` rejects anything outside the closed
allowlist with a :class:`MetricGrammarError`.
"""

from __future__ import annotations

import pytest
from valuemaxx.core import MetricDefinition
from valuemaxx.metrics.errors import MetricGrammarError
from valuemaxx.metrics.grammar import (
    ALLOWED_FILTER_FIELDS,
    DENOMINATOR_TOKENS,
    NUMERATOR_TOKENS,
    Dimension,
    validate_definition,
)


def _definition(
    *,
    name: str = "cost_per_outcome",
    numerator: str = "total_cost_usd",
    denominator: str = "verified_outcome_count",
    filters: dict[str, str] | None = None,
    group_by: tuple[str, ...] = (),
) -> MetricDefinition:
    return MetricDefinition(
        name=name,
        numerator=numerator,
        denominator=denominator,
        filters=filters or {},
        group_by=group_by,
    )


def test_a_clean_definition_validates() -> None:
    """A definition built entirely from allowlisted tokens validates and round-trips."""
    definition = _definition(filters={"provider": "anthropic"}, group_by=("model",))
    assert validate_definition(definition) is definition


def test_unknown_numerator_token_rejected() -> None:
    """A numerator measure outside the closed allowlist is a grammar error."""
    with pytest.raises(MetricGrammarError, match="numerator"):
        validate_definition(_definition(numerator="DROP TABLE costs"))


def test_unknown_denominator_token_rejected() -> None:
    """A denominator measure outside the closed allowlist is a grammar error."""
    with pytest.raises(MetricGrammarError, match="denominator"):
        validate_definition(_definition(denominator="all_outcomes_ever"))


def test_free_text_sql_in_filter_value_rejected() -> None:
    """A filter value carrying SQL/semicolons is not a member of the value allowlist."""
    with pytest.raises(MetricGrammarError, match="filter"):
        validate_definition(_definition(filters={"provider": "x'; DROP TABLE costs;--"}))


def test_eval_marker_in_filter_value_rejected() -> None:
    """A filter value carrying an ``eval(`` marker is rejected (no_eval_in_predicate)."""
    with pytest.raises(MetricGrammarError):
        validate_definition(_definition(filters={"provider": "eval(payload)"}))


def test_unknown_filter_field_rejected() -> None:
    """A filter keyed on a field outside the allowlist is a grammar error."""
    with pytest.raises(MetricGrammarError, match="filter field"):
        validate_definition(_definition(filters={"raw_sql": "anything"}))


def test_unknown_group_by_dimension_rejected() -> None:
    """A group_by dimension outside the closed Dimension allowlist is a grammar error."""
    with pytest.raises(MetricGrammarError, match="dimension"):
        validate_definition(_definition(group_by=("totally_made_up",)))


def test_cost_per_outcome_requires_verified_outcome_denominator() -> None:
    """``cost_per_outcome`` numerator REQUIRES denominator=verified_outcome_count."""
    with pytest.raises(MetricGrammarError, match="verified_outcome_count"):
        validate_definition(
            _definition(numerator="total_cost_usd", denominator="attempt_count")
        )


def test_ratio_measure_pairs_allowed() -> None:
    """A non-cost-per-outcome ratio (e.g. attempt_count over outcome_count) validates."""
    definition = _definition(
        name="attempts_per_outcome",
        numerator="attempt_count",
        denominator="outcome_count",
    )
    assert validate_definition(definition) is definition


def test_every_dimension_is_an_allowed_group_by() -> None:
    """Every member of the Dimension allowlist is accepted as a group_by token."""
    for dimension in Dimension:
        assert validate_definition(_definition(group_by=(dimension.value,))) is not None


def test_numerator_carrying_sql_marker_is_rejected_as_free_text() -> None:
    """A numerator token bearing an SQL marker is rejected by the free-text guard."""
    with pytest.raises(MetricGrammarError, match="forbidden construct"):
        validate_definition(_definition(numerator="cost; DROP"))


def test_group_by_carrying_marker_is_rejected_as_free_text() -> None:
    """A group_by dimension bearing a forbidden marker is rejected by the free-text guard."""
    with pytest.raises(MetricGrammarError, match="forbidden construct"):
        validate_definition(_definition(group_by=("model;--",)))


def test_allowlists_are_closed_frozensets() -> None:
    """The allowlists are immutable closed sets, not open/extendable containers."""
    assert isinstance(NUMERATOR_TOKENS, frozenset)
    assert isinstance(DENOMINATOR_TOKENS, frozenset)
    assert isinstance(ALLOWED_FILTER_FIELDS, frozenset)
