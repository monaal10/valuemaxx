"""VALIDATE — check a proposed rule against the core Protocols (design §7 step 4).

:func:`validate_rule` enforces two invariants on an
:class:`~valuemaxx.onboarding.capabilities.OutcomeRuleCandidate` before it can be
rendered into config:

1. **Safe predicate** — the ``when`` expression passes the injected
   :class:`~valuemaxx.core.OutcomesPredicateValidator` (the AST allowlist; the
   ``no_eval_in_predicate`` guardrail). Any rejection is surfaced as
   :class:`~valuemaxx.onboarding.errors.UnsafePredicateError`.
2. **System-owned signal** — the rule's ``signal`` must equal what the
   :class:`~valuemaxx.core.SignalClassMapper` assigns for the rule's match kind. A
   rule that claims ``outcome_confirmed`` on a site the system maps to
   ``action_attempted`` is a tampered signal and is rejected (the
   ``signal_class_never_user_set`` guardrail) — an attempt can never masquerade as a
   confirmed outcome.

The validator is coded against the **Protocols**, never a concrete implementation —
the real outcomes validator/mapper is injected at the service boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.core import SignalClass
from valuemaxx.onboarding.errors import UnsafePredicateError

if TYPE_CHECKING:
    from valuemaxx.core import OutcomesPredicateValidator, SignalClassMapper
    from valuemaxx.onboarding.capabilities import OutcomeRuleCandidate


def validate_rule(
    rule: OutcomeRuleCandidate,
    *,
    predicate_validator: OutcomesPredicateValidator,
    signal_mapper: SignalClassMapper,
) -> None:
    """Validate ``rule``; raise :class:`UnsafePredicateError` on any violation.

    Checks the ``when`` predicate against the AST allowlist and re-asserts that the
    rule's signal class equals the system-mapped value for its match kind. Returns
    None on success (the rule is safe to render).
    """
    try:
        predicate_validator.validate(rule.when)
    except UnsafePredicateError:
        raise
    except Exception as exc:
        raise UnsafePredicateError(f"unsafe predicate {rule.when!r}: {exc}") from exc

    expected = SignalClass(signal_mapper.map_signal(match_kind=rule.match_kind, declared=""))
    if rule.signal is not expected:
        raise UnsafePredicateError(
            f"signal {rule.signal.value!r} is not the system-mapped signal "
            f"{expected.value!r} for match kind {rule.match_kind!r}; the signal class "
            "is system-owned and never user-set"
        )


__all__ = ["validate_rule"]
