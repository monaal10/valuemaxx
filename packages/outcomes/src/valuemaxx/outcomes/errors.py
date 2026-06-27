"""Typed errors for the outcomes package (AGENTS.md §5 — errors are typed, explicit).

These extend :class:`~valuemaxx.core.errors.AtmError` so the whole product shares one
exception root. Parse/validation failures are surfaced to the *authoring* path
(onboarding agent, ``validate_outcome_rule`` capability); the runtime instrumentation
path never raises into the host (it fails open, §5 SDK-never-crashes-the-host).
"""

from __future__ import annotations

from valuemaxx.core import AtmError


class OutcomeRuleError(AtmError):
    """Base error for an invalid or unusable outcome rule."""


class PredicateValidationError(OutcomeRuleError):
    """A ``when``/``value`` expression used a construct outside the AST allowlist.

    Raised by :class:`~valuemaxx.outcomes.predicate.SafePredicateValidator` when an
    expression references ``eval``/``exec``/a dunder/an unknown call — the predicate
    DSL is never ``eval``'d, so anything it cannot prove safe is rejected at author
    time (the ``no_eval_in_predicate`` conformance rule).
    """


class OutcomeRuleSchemaError(OutcomeRuleError):
    """An ``outcomes.yaml`` document violated the rule schema (e.g. not exactly one match kind)."""


__all__ = [
    "OutcomeRuleError",
    "OutcomeRuleSchemaError",
    "PredicateValidationError",
]
