"""F0-CORE-1b: the H7 conservative-propagation heart (property-tested).

The rollup can never look *more* certain than its least-trusted member. Both
``minimum_tier`` and ``confidence_distribution`` are required and serialized, so
no surface can silently collapse "1 exact + 50 candidate" into a clean number.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from atm_core.enums import BindingTier, ConfidenceLabel, EvalGrade, Provenance, TokenClass
from atm_core.ids import RunId, TenantId
from atm_core.rollup import RollupConfidence, RunCostRollup, compose_label
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

_ALL_TIERS = list(BindingTier)
# least-trusted -> most-trusted (mirrors atm_core.rollup._TIER_ORDER)
_ORDER = (
    BindingTier.LIKELY,
    BindingTier.CANDIDATE,
    BindingTier.DETERMINISTIC,
    BindingTier.EXACT,
)


def _tenant() -> TenantId:
    return TenantId(uuid4())


# ---- RollupConfidence.propagate / validator (the heart) --------------------


def test_propagate_minimum_is_least_trusted() -> None:
    """T-PROP-1: minimum_tier is the least-trusted present tier."""
    rc = RollupConfidence.propagate([BindingTier.EXACT, BindingTier.CANDIDATE])
    assert rc.minimum_tier is BindingTier.CANDIDATE


def test_propagate_counts_match_input_length() -> None:
    """T-PROP-2: the distribution counts sum to the number of inputs."""
    tiers = [BindingTier.EXACT, BindingTier.EXACT, BindingTier.LIKELY]
    rc = RollupConfidence.propagate(tiers)
    assert sum(rc.confidence_distribution.values()) == len(tiers)
    assert rc.confidence_distribution[BindingTier.EXACT] == 2
    assert rc.confidence_distribution[BindingTier.LIKELY] == 1


def test_one_exact_fifty_candidate_cannot_look_clean() -> None:
    """T-PROP-3: 1 exact + 50 candidate -> minimum_tier candidate, both shown."""
    tiers = [BindingTier.EXACT] + [BindingTier.CANDIDATE] * 50
    rc = RollupConfidence.propagate(tiers)
    assert rc.minimum_tier is BindingTier.CANDIDATE
    assert rc.confidence_distribution[BindingTier.EXACT] == 1
    assert rc.confidence_distribution[BindingTier.CANDIDATE] == 50


def test_validator_rejects_inconsistent_minimum() -> None:
    """T-PROP-5: minimum_tier=EXACT with a CANDIDATE in the distribution is rejected."""
    with pytest.raises(ValidationError):
        RollupConfidence(
            minimum_tier=BindingTier.EXACT,
            confidence_distribution={BindingTier.CANDIDATE: 3},
        )


def test_validator_rejects_empty_distribution() -> None:
    with pytest.raises(ValidationError):
        RollupConfidence(
            minimum_tier=BindingTier.EXACT,
            confidence_distribution={},
        )


def test_validator_ignores_zero_counts_for_presence() -> None:
    """A zero count does not make a tier 'present' for the minimum computation."""
    rc = RollupConfidence(
        minimum_tier=BindingTier.EXACT,
        confidence_distribution={BindingTier.EXACT: 2, BindingTier.CANDIDATE: 0},
    )
    assert rc.minimum_tier is BindingTier.EXACT


def test_propagate_empty_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        RollupConfidence.propagate([])


def test_both_h7_fields_round_trip_json() -> None:
    """T-PROP-6: both H7 fields survive a model_dump_json round-trip."""
    rc = RollupConfidence.propagate([BindingTier.EXACT, BindingTier.LIKELY])
    restored = RollupConfidence.model_validate_json(rc.model_dump_json())
    assert restored == rc
    assert "minimum_tier" in rc.model_dump()
    assert "confidence_distribution" in rc.model_dump()


@given(st.lists(st.sampled_from(_ALL_TIERS), min_size=1, max_size=40))
def test_propagate_minimum_is_least_trusted_property(tiers: list[BindingTier]) -> None:
    """T-PROP-1 (property): for any non-empty tier list, minimum is least-trusted."""
    rc = RollupConfidence.propagate(tiers)
    present = set(tiers)
    expected = min(present, key=_ORDER.index)
    assert rc.minimum_tier is expected
    assert sum(rc.confidence_distribution.values()) == len(tiers)


@given(
    st.lists(st.sampled_from(_ALL_TIERS), min_size=1, max_size=20),
    st.lists(st.sampled_from(_ALL_TIERS), min_size=1, max_size=20),
)
def test_aggregation_never_raises_confidence_property(
    a: list[BindingTier], b: list[BindingTier]
) -> None:
    """T-PROP-4 (property): merging two groups never produces a MORE trusted minimum."""
    merged = RollupConfidence.propagate(a + b)
    rc_a = RollupConfidence.propagate(a)
    rc_b = RollupConfidence.propagate(b)
    # the merged minimum is no more trusted than the least-trusted of the parts
    assert _ORDER.index(merged.minimum_tier) <= _ORDER.index(rc_a.minimum_tier)
    assert _ORDER.index(merged.minimum_tier) <= _ORDER.index(rc_b.minimum_tier)


# ---- compose_label (§3.1) --------------------------------------------------


def test_compose_label_all_best_is_high() -> None:
    label = compose_label(
        provenances=[Provenance.MEASURED, Provenance.PROVIDER_RECONCILED],
        tiers=[BindingTier.EXACT, BindingTier.DETERMINISTIC],
        signals=[],
    )
    assert label is ConfidenceLabel.HIGH


def test_compose_label_any_estimated_is_low() -> None:
    label = compose_label(
        provenances=[Provenance.MEASURED, Provenance.ESTIMATED],
        tiers=[BindingTier.EXACT],
        signals=[],
    )
    assert label is ConfidenceLabel.LOW


def test_compose_label_any_likely_is_low() -> None:
    label = compose_label(
        provenances=[Provenance.MEASURED],
        tiers=[BindingTier.EXACT, BindingTier.LIKELY],
        signals=[],
    )
    assert label is ConfidenceLabel.LOW


def test_compose_label_directional_eval_is_low() -> None:
    label = compose_label(
        provenances=[Provenance.MEASURED],
        tiers=[BindingTier.EXACT],
        signals=[],
        eval_grade=EvalGrade.DIRECTIONAL,
    )
    assert label is ConfidenceLabel.LOW


def test_compose_label_mixed_candidate_is_medium() -> None:
    label = compose_label(
        provenances=[Provenance.ALLOCATED],
        tiers=[BindingTier.CANDIDATE],
        signals=[],
    )
    assert label is ConfidenceLabel.MEDIUM


# ---- RunCostRollup ---------------------------------------------------------


def test_run_cost_rollup_carries_both_h7_fields() -> None:
    """A RunCostRollup carries a RollupConfidence with both H7 fields."""
    rollup = RunCostRollup(
        tenant_id=_tenant(),
        run_id=RunId("run-1"),
        total_cost_usd=Decimal("1.50"),
        by_token_class={TokenClass.OUTPUT: Decimal("1.50")},
        provenance_breakdown={Provenance.MEASURED: Decimal("1.50")},
        confidence=RollupConfidence.propagate([BindingTier.EXACT]),
    )
    assert rollup.confidence.minimum_tier is BindingTier.EXACT
    assert rollup.confidence.confidence_distribution[BindingTier.EXACT] == 1
    # both fields present on the serialized rollup
    dumped = rollup.model_dump()
    assert "minimum_tier" in dumped["confidence"]
    assert "confidence_distribution" in dumped["confidence"]


def test_run_cost_rollup_requires_tenant() -> None:
    with pytest.raises(ValidationError):
        RunCostRollup(  # type: ignore[call-arg]
            run_id=RunId("run-1"),
            total_cost_usd=Decimal("1.50"),
            by_token_class={},
            provenance_breakdown={},
            confidence=RollupConfidence.propagate([BindingTier.EXACT]),
        )
