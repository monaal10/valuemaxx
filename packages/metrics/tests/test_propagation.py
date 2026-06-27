"""Propagation tests — the H7 (conservative confidence) + H8 (retraction) heart.

Aggregation NEVER raises confidence: a rollup's ``minimum_tier`` is the
least-trusted present member. Candidate/likely outcomes are EXCLUDED from the
billing-grade denominator but still COUNTED in the distribution. Retracted
outcomes are EXCLUDED from the denominator and counted separately so the metric
can be re-emitted annotated (never silently left).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from valuemaxx.core import (
    BindingTier,
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    SignalClass,
    TenantId,
)
from valuemaxx.metrics.propagation import (
    DenominatorBreakdown,
    denominator_outcomes,
    is_billing_grade,
    propagate,
)

_TENANT = TenantId(uuid4())


def _outcome(
    *,
    signal_class: SignalClass,
    tier: BindingTier | None,
    name: str = "signup",
) -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=_TENANT,
        id=OutcomeEventId(f"oe-{uuid4()}"),
        name=name,
        signal_class=signal_class,
        value=Decimal("1"),
        occurred_at=datetime(2026, 6, 27, tzinfo=UTC),
        binding=OutcomeBinding(run_id=None, tier=tier, bound_by="t1" if tier else None),
        entity_keys=frozenset(),
        correlation_id=None,
        source="test",
        raw={},
    )


def test_propagate_takes_minimum_tier() -> None:
    """A mix of exact + candidate propagates to minimum_tier=CANDIDATE (never EXACT)."""
    confidence = propagate([BindingTier.EXACT, BindingTier.CANDIDATE, BindingTier.EXACT])
    assert confidence.minimum_tier is BindingTier.CANDIDATE


def test_propagate_counts_every_member() -> None:
    """The distribution counts equal the number of input tiers (nothing dropped)."""
    tiers = [BindingTier.EXACT] + [BindingTier.CANDIDATE] * 50
    confidence = propagate(tiers)
    assert sum(confidence.confidence_distribution.values()) == 51
    assert confidence.minimum_tier is BindingTier.CANDIDATE


def test_propagate_single_exact_among_many_candidates_cannot_look_clean() -> None:
    """1 exact + 50 candidate: headline is CANDIDATE and both fields are shown."""
    confidence = propagate([BindingTier.EXACT, *([BindingTier.CANDIDATE] * 50)])
    assert confidence.minimum_tier is BindingTier.CANDIDATE
    assert confidence.confidence_distribution[BindingTier.EXACT] == 1
    assert confidence.confidence_distribution[BindingTier.CANDIDATE] == 50


def test_propagate_empty_raises() -> None:
    """Propagating with no members has no defined minimum tier — it raises."""
    with pytest.raises(ValueError, match="at least one"):
        propagate([])


def test_is_billing_grade_only_exact_and_deterministic() -> None:
    """Only exact/deterministic are billing-grade; candidate/likely never are."""
    assert is_billing_grade(BindingTier.EXACT) is True
    assert is_billing_grade(BindingTier.DETERMINISTIC) is True
    assert is_billing_grade(BindingTier.CANDIDATE) is False
    assert is_billing_grade(BindingTier.LIKELY) is False


def test_denominator_excludes_candidate_but_counts_it() -> None:
    """2 exact + 3 candidate -> denominator 2, but all 5 counted in the distribution."""
    outcomes = [
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT),
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT),
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.CANDIDATE),
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.CANDIDATE),
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.CANDIDATE),
    ]
    breakdown = denominator_outcomes(outcomes)
    assert breakdown.verified_count == 2
    assert breakdown.advisory_excluded_count == 3
    assert breakdown.retracted_excluded_count == 0
    assert breakdown.tier_distribution[BindingTier.EXACT] == 2
    assert breakdown.tier_distribution[BindingTier.CANDIDATE] == 3


def test_denominator_excludes_retracted_and_counts_it_for_reemit() -> None:
    """A retracted outcome is removed from the denominator and counted for re-emit (H8)."""
    outcomes = [
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT),
        _outcome(signal_class=SignalClass.OUTCOME_RETRACTED, tier=BindingTier.EXACT),
    ]
    breakdown = denominator_outcomes(outcomes)
    assert breakdown.verified_count == 1
    assert breakdown.retracted_excluded_count == 1


def test_denominator_excludes_action_attempted() -> None:
    """An action_attempted outcome is not a confirmed outcome — not in the denominator."""
    outcomes = [
        _outcome(signal_class=SignalClass.ACTION_ATTEMPTED, tier=BindingTier.EXACT),
        _outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=BindingTier.EXACT),
    ]
    breakdown = denominator_outcomes(outcomes)
    assert breakdown.verified_count == 1
    assert breakdown.attempted_excluded_count == 1


def test_denominator_excludes_confirmed_with_no_binding_tier() -> None:
    """A confirmed-but-unbound outcome (tier=None) is not billing-grade."""
    outcomes = [_outcome(signal_class=SignalClass.OUTCOME_CONFIRMED, tier=None)]
    breakdown = denominator_outcomes(outcomes)
    assert breakdown.verified_count == 0
    assert breakdown.advisory_excluded_count == 1


def test_breakdown_is_a_dataclass_with_counter() -> None:
    """The breakdown's tier distribution is a Counter (counts, never dropped)."""
    breakdown = denominator_outcomes([])
    assert isinstance(breakdown, DenominatorBreakdown)
    assert isinstance(breakdown.tier_distribution, Counter)
    assert breakdown.verified_count == 0


@given(
    tiers=st.lists(
        st.sampled_from(list(BindingTier)),
        min_size=1,
        max_size=40,
    )
)
def test_aggregate_minimum_never_exceeds_any_member(tiers: list[BindingTier]) -> None:
    """Property: the aggregated minimum_tier is never more trusted than any member.

    Aggregation can only lower or hold confidence — never raise it (§3.1 H7).
    """
    order = (
        BindingTier.LIKELY,
        BindingTier.CANDIDATE,
        BindingTier.DETERMINISTIC,
        BindingTier.EXACT,
    )
    confidence = propagate(tiers)
    minimum_rank = order.index(confidence.minimum_tier)
    assert all(minimum_rank <= order.index(tier) for tier in tiers)
    assert sum(confidence.confidence_distribution.values()) == len(tiers)
