"""Conservative confidence propagation (H7) + retraction handling (H8).

Two honesty invariants live here:

* **H7 — aggregation never raises confidence.** A rollup's headline tier is the
  *least-trusted* member tier. :func:`propagate` defers to the core
  :class:`~valuemaxx.core.RollupConfidence` (the single source for the tier
  ordering and the both-fields invariant) — it counts every member and takes the
  minimum, so "1 exact + 50 candidate" can never render as clean.

* **H8 — the billing-grade denominator is honest.** :func:`denominator_outcomes`
  counts toward the cost-per-outcome denominator ONLY confirmed outcomes bound at
  an exact/deterministic tier. Candidate/likely (advisory) outcomes are EXCLUDED
  from the denominator but still counted; ``action_attempted`` outcomes are not
  outcomes yet; ``outcome_retracted`` outcomes are excluded and counted
  separately so the metric is re-emitted annotated, never silently left.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from valuemaxx.core import BindingTier, RollupConfidence, SignalClass

if TYPE_CHECKING:
    from collections.abc import Iterable

    from valuemaxx.core import OutcomeEvent

# The billing-grade tiers (§3.1): only exact/deterministic bindings count toward a
# billing-grade denominator. candidate/likely are advisory and review-queued.
_BILLING_GRADE_TIERS: frozenset[BindingTier] = frozenset(
    {BindingTier.EXACT, BindingTier.DETERMINISTIC}
)


def propagate(tiers: Iterable[BindingTier]) -> RollupConfidence:
    """Aggregate member tiers into a :class:`~valuemaxx.core.RollupConfidence`.

    Counts every member tier and sets ``minimum_tier`` to the least-trusted
    present tier — aggregation never raises confidence (§3.1 H7). Raises
    ``ValueError`` if no member tiers are supplied (there is no defined minimum of
    an empty rollup). Delegates to the core ``RollupConfidence.propagate`` so the
    tier ordering and both-fields invariant are defined exactly once.
    """
    return RollupConfidence.propagate(tiers)


def is_billing_grade(tier: BindingTier) -> bool:
    """True iff ``tier`` is billing-grade (exact/deterministic only; §3.1).

    candidate/likely are advisory and never billing-grade, so they never count
    toward a billing-grade denominator.
    """
    return tier in _BILLING_GRADE_TIERS


@dataclass(frozen=True, slots=True)
class DenominatorBreakdown:
    """The honest split of a set of outcomes for the cost-per-outcome denominator.

    Attributes:
        verified_count: confirmed outcomes bound at an exact/deterministic tier —
            the ONLY outcomes that count toward the billing-grade denominator.
        advisory_excluded_count: confirmed outcomes excluded because their binding
            is advisory (candidate/likely) or absent — counted, never in the
            denominator (§3.1).
        attempted_excluded_count: ``action_attempted`` outcomes — not confirmed
            outcomes yet, so excluded from the denominator.
        retracted_excluded_count: ``outcome_retracted`` outcomes excluded from the
            denominator; counted so the metric is re-emitted annotated (§3.1 H8).
        tier_distribution: the count of every present binding tier across ALL
            confirmed/retracted outcomes (nothing dropped) — the H7 distribution.
    """

    verified_count: int
    advisory_excluded_count: int
    attempted_excluded_count: int
    retracted_excluded_count: int
    tier_distribution: Counter[BindingTier] = field(
        default_factory=lambda: Counter[BindingTier]()
    )


def denominator_outcomes(outcomes: Iterable[OutcomeEvent]) -> DenominatorBreakdown:
    """Split ``outcomes`` into the billing-grade denominator and its exclusions.

    An outcome counts toward ``verified_count`` iff it is ``outcome_confirmed`` AND
    bound at a billing-grade tier (exact/deterministic). Advisory (candidate/likely
    or unbound) confirmed outcomes are excluded-but-counted; ``action_attempted``
    outcomes are excluded as not-yet-outcomes; ``outcome_retracted`` outcomes are
    excluded and counted in ``retracted_excluded_count`` so the metric can be
    re-emitted annotated rather than silently left (§3.1 H8). Every confirmed or
    retracted outcome's binding tier is tallied into ``tier_distribution`` so the
    H7 distribution never drops a member.
    """
    verified = 0
    advisory_excluded = 0
    attempted_excluded = 0
    retracted_excluded = 0
    tier_distribution: Counter[BindingTier] = Counter()

    for outcome in outcomes:
        signal = outcome.signal_class
        tier = outcome.binding.tier

        if signal is SignalClass.ACTION_ATTEMPTED:
            attempted_excluded += 1
            continue

        if tier is not None:
            tier_distribution[tier] += 1

        if signal is SignalClass.OUTCOME_RETRACTED:
            retracted_excluded += 1
            continue

        # signal is OUTCOME_CONFIRMED here.
        if tier is not None and is_billing_grade(tier):
            verified += 1
        else:
            advisory_excluded += 1

    return DenominatorBreakdown(
        verified_count=verified,
        advisory_excluded_count=advisory_excluded,
        attempted_excluded_count=attempted_excluded,
        retracted_excluded_count=retracted_excluded,
        tier_distribution=tier_distribution,
    )


__all__ = [
    "DenominatorBreakdown",
    "denominator_outcomes",
    "is_billing_grade",
    "propagate",
]
