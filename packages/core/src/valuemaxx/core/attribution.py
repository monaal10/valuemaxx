"""AttributionCandidate + AttributionResult — the binding cascade output (§6.3).

A result is *billing-grade* only when its tier is ``exact`` or ``deterministic``;
``candidate`` and ``likely`` are advisory, review-queued, and never fed to
billing-grade metrics (§4, §13).
"""

from __future__ import annotations

from valuemaxx.core.base import StrictModel, TenantScopedModel
from valuemaxx.core.enums import BindingTier
from valuemaxx.core.ids import OutcomeEventId, RunId

_BILLING_GRADE_TIERS = frozenset({BindingTier.EXACT, BindingTier.DETERMINISTIC})


class AttributionCandidate(StrictModel):
    """One candidate run an outcome might bind to, with its tier, score, rationale."""

    run_id: RunId
    tier: BindingTier
    score: float
    rationale: str


class AttributionResult(TenantScopedModel):
    """The resolved (or review-queued) binding of one outcome to a run."""

    outcome_id: OutcomeEventId
    run_id: RunId | None
    tier: BindingTier | None
    bound_by: str | None
    candidates: tuple[AttributionCandidate, ...]
    review_required: bool

    @property
    def is_billing_grade(self) -> bool:
        """True only for exact/deterministic — candidate/likely are never billing-grade."""
        return self.tier in _BILLING_GRADE_TIERS


__all__ = ["AttributionCandidate", "AttributionResult"]
