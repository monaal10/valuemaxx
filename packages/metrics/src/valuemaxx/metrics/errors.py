"""Typed errors for the metrics package (AGENTS.md §5 — errors are typed, explicit).

These extend :class:`~valuemaxx.core.AtmError` so the whole product shares one
exception root. Grammar/validation failures are surfaced to the *authoring* path
(the ``run_metric`` capability, the onboarding agent), never swallowed.
"""

from __future__ import annotations

from valuemaxx.core import AtmError


class MetricError(AtmError):
    """Base error for an invalid or unusable metric."""


class MetricGrammarError(MetricError):
    """A metric definition used a token outside the closed allowlist DSL.

    Raised by :func:`~valuemaxx.metrics.grammar.validate_definition` when a metric
    references a measure/dimension/filter outside the typed allowlist, embeds
    free-text SQL or an ``eval``/``exec`` marker, or pairs an incompatible
    numerator/denominator (e.g. a ``cost_per_outcome`` numerator without the
    ``verified_outcome_count`` denominator). The grammar is never ``eval``'d, so
    anything it cannot prove is a member of the allowlist is rejected at author
    time (the ``no_eval_in_predicate`` conformance rule).
    """


__all__ = ["MetricError", "MetricGrammarError"]
