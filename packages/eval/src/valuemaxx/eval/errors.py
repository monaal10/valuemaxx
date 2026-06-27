"""Typed errors for the eval package (AGENTS.md §5 — errors are typed, explicit).

These extend :class:`~valuemaxx.core.AtmError` so the whole product shares one
exception root; downstream code catches :class:`EvalError` (or a specific
subclass), never the bare ``Exception``.

The specific failures encode the eval funnel's hard refusals (§8): a cost gate
that exceeds budget, a phase invoked out of order, ground truth that is not
available for the requested rung, and an LLM judge that has not been validated
against human labels.
"""

from __future__ import annotations

from valuemaxx.core import AtmError


class EvalError(AtmError):
    """Base error for the eval-backed model-recommendation funnel (§8)."""


class BudgetExceededError(EvalError):
    """A cost gate refused to start because the estimate exceeded the budget (§8.5).

    The estimate IS the consent: when ``est > budget`` the gate refuses rather
    than silently starting an expensive run.
    """


class GateNotApprovedError(EvalError):
    """A gated stage was reached without the required approval (§8.5 M2).

    Raised when phase-2 (the projected full-run) is attempted before phase-1 (the
    smoke-eval) has been approved — the ``two_phase_gate_ordered`` invariant.
    """


class GroundTruthUnavailableError(EvalError):
    """No usable ground-truth rung was available to grade a case (§8.2).

    Raised when neither outcome-label (on a reconstructable task) nor any labeled
    fallback (human / validated judge / reference) can produce a grade.
    """


class JudgeNotValidatedError(EvalError):
    """An LLM judge was used to grade without passing human-label validation (§8.2).

    A judge is usable only after TPR/TNR >= 0.9 against a committed N >= 50 human
    fixture; an unvalidated judge is refused rather than silently trusted.
    """


__all__ = [
    "BudgetExceededError",
    "EvalError",
    "GateNotApprovedError",
    "GroundTruthUnavailableError",
    "JudgeNotValidatedError",
]
