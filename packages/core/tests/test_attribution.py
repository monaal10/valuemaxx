"""F0-CORE-1b: AttributionCandidate + AttributionResult — billing-grade gate."""

from __future__ import annotations

from uuid import uuid4

import pytest
from atm_core.attribution import AttributionCandidate, AttributionResult
from atm_core.enums import BindingTier
from atm_core.ids import OutcomeEventId, RunId, TenantId


def _tenant() -> TenantId:
    return TenantId(uuid4())


def _result(tier: BindingTier | None, **overrides: object) -> AttributionResult:
    base: dict[str, object] = {
        "tenant_id": _tenant(),
        "outcome_id": OutcomeEventId("oe-1"),
        "run_id": RunId("run-1") if tier else None,
        "tier": tier,
        "bound_by": "t1" if tier else None,
        "candidates": (),
        "review_required": tier in (BindingTier.CANDIDATE, BindingTier.LIKELY),
    }
    base.update(overrides)
    return AttributionResult(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (BindingTier.EXACT, True),
        (BindingTier.DETERMINISTIC, True),
        (BindingTier.CANDIDATE, False),
        (BindingTier.LIKELY, False),
        (None, False),
    ],
)
def test_is_billing_grade(tier: BindingTier | None, expected: bool) -> None:
    """T-AR-1: only exact/deterministic are billing-grade; candidate/likely never."""
    assert _result(tier).is_billing_grade is expected


def test_candidate_carries_score_and_rationale() -> None:
    cand = AttributionCandidate(
        run_id=RunId("run-1"),
        tier=BindingTier.CANDIDATE,
        score=0.7,
        rationale="shared customer_id within 5m",
    )
    assert cand.tier is BindingTier.CANDIDATE
    assert cand.score == 0.7


def test_result_with_candidates() -> None:
    cand = AttributionCandidate(
        run_id=RunId("run-2"),
        tier=BindingTier.CANDIDATE,
        score=0.5,
        rationale="entity match",
    )
    result = _result(BindingTier.CANDIDATE, candidates=(cand,), review_required=True)
    assert result.candidates[0].run_id == RunId("run-2")
    assert result.review_required is True
