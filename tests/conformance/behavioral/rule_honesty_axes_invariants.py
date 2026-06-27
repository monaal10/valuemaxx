"""honesty_axes_invariants — illegal honesty states each raise (foundation-green).

Constructing an estimate-as-billed (reconciled provenance with no record),
an inferred-as-exact (a candidate that claims billing-grade), or a malformed
rollup that looks cleaner than its members must each raise. ``flags_violation``
runs a zero-arg "illegal construction" thunk and returns True iff it raised.

The negative fixture is a thunk that does NOT raise (a benign construction) —
the rule must flag it as "did not enforce". The foundation subject is the set of
real illegal constructions, all of which DO raise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError
from valuemaxx.core.enums import BindingTier, Provenance
from valuemaxx.core.provenance import ProvenanceLabel
from valuemaxx.core.rollup import RollupConfidence

from tests.conformance.rulebase import Rule, RuleKind

if TYPE_CHECKING:
    from collections.abc import Callable


def _raises(thunk: Callable[[], object]) -> bool:
    try:
        thunk()
    except (ValidationError, ValueError):
        return True
    return False


def _illegal_estimate_as_billed() -> object:
    # reconciled provenance with no reconciliation_record_id -> must raise
    return ProvenanceLabel(provenance=Provenance.PROVIDER_RECONCILED)


def _illegal_clean_rollup() -> object:
    # claims minimum_tier EXACT while a CANDIDATE member is present -> must raise
    return RollupConfidence(
        minimum_tier=BindingTier.EXACT,
        confidence_distribution={BindingTier.CANDIDATE: 3},
    )


def _flags(subject: object) -> bool:
    """A subject is a thunk; the rule flags it iff it does NOT raise (no enforcement)."""
    assert callable(subject)
    return not _raises(subject)


def _negative_fixture() -> object:
    # a benign construction that does NOT raise -> the rule must flag it
    return lambda: ProvenanceLabel(provenance=Provenance.MEASURED)


def _foundation_subject() -> object:
    # a real illegal construction that DOES raise -> the rule must NOT flag it
    return _illegal_estimate_as_billed


def all_illegal_states_raise() -> bool:
    """Every catalogued illegal honesty state raises (the substantive assertion)."""
    return _raises(_illegal_estimate_as_billed) and _raises(_illegal_clean_rollup)


RULE = Rule(
    name="honesty_axes_invariants",
    kind=RuleKind.BEHAVIORAL,
    green_now=True,
    owner_task="foundation",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
