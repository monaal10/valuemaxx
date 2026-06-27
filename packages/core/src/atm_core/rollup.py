"""The H7 conservative-propagation heart (§3.1).

Every rollup output carries BOTH a ``minimum_tier`` (the least-trusted member
tier — the headline label a surface must show) AND a ``confidence_distribution``
(so no surface can collapse "1 exact + 50 candidate" into a clean number). Both
fields are required and serialized; aggregation can never raise confidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal

from pydantic import model_validator

from atm_core.base import StrictModel, TenantScopedModel
from atm_core.enums import BindingTier, ConfidenceLabel, EvalGrade, Provenance, TokenClass
from atm_core.ids import RunId

# Least-trusted -> most-trusted. The minimum_tier is the least-trusted *present*
# member, so a single low-tier member drags the headline down (conservative).
_TIER_ORDER: tuple[BindingTier, ...] = (
    BindingTier.LIKELY,
    BindingTier.CANDIDATE,
    BindingTier.DETERMINISTIC,
    BindingTier.EXACT,
)


def _least_trusted(tiers: Iterable[BindingTier]) -> BindingTier:
    return min(tiers, key=_TIER_ORDER.index)


class RollupConfidence(StrictModel):
    """The both-fields H7 confidence carried by every rollup-shaped model."""

    minimum_tier: BindingTier
    confidence_distribution: Mapping[BindingTier, int]

    @model_validator(mode="after")
    def _distribution_consistency(self) -> RollupConfidence:
        """minimum_tier must equal the least-trusted tier actually present (count > 0)."""
        present = {tier for tier, count in self.confidence_distribution.items() if count > 0}
        if not present:
            raise ValueError(
                "confidence_distribution must contain at least one tier with a positive count"
            )
        expected = _least_trusted(present)
        if self.minimum_tier is not expected:
            raise ValueError(
                f"minimum_tier {self.minimum_tier.value!r} is not the least-trusted present "
                f"tier {expected.value!r}; a rollup may never look more certain than its "
                "least-trusted member (§3.1 H7)"
            )
        return self

    @classmethod
    def propagate(cls, tiers: Iterable[BindingTier]) -> RollupConfidence:
        """Build a confidence from member tiers: count them, take the least-trusted."""
        tier_list = list(tiers)
        if not tier_list:
            raise ValueError("propagate requires at least one member tier")
        distribution: dict[BindingTier, int] = {}
        for tier in tier_list:
            distribution[tier] = distribution.get(tier, 0) + 1
        return cls(minimum_tier=_least_trusted(tier_list), confidence_distribution=distribution)


def compose_label(
    *,
    provenances: Iterable[Provenance],
    tiers: Iterable[BindingTier],
    signals: Iterable[object],
    eval_grade: EvalGrade | None = None,
) -> ConfidenceLabel:
    """Map the contributing axes to a single user-facing label (§3.1).

    The displayed confidence is the *minimum* across all contributing axes:
      - all-best (measured/provider_reconciled + exact/deterministic) -> HIGH;
      - any estimated provenance, any ``likely`` tier, or a ``directional`` eval
        grade -> LOW (the weakest evidence dominates);
      - otherwise (any ``candidate`` tier or ``allocated`` provenance) -> MEDIUM.

    ``signals`` participates in the API surface for symmetry with the three axes
    but does not currently lower the label below what provenance/tier imply.
    """
    _ = list(signals)  # reserved: signal class participates in the composed label surface
    prov_set = set(provenances)
    tier_set = set(tiers)

    if eval_grade is EvalGrade.DIRECTIONAL:
        return ConfidenceLabel.LOW
    if Provenance.ESTIMATED in prov_set or BindingTier.LIKELY in tier_set:
        return ConfidenceLabel.LOW
    if Provenance.ALLOCATED in prov_set or BindingTier.CANDIDATE in tier_set:
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.HIGH


class RunCostRollup(TenantScopedModel):
    """A per-run cost rollup carrying the provenance breakdown + H7 confidence."""

    run_id: RunId
    total_cost_usd: Decimal
    by_token_class: Mapping[TokenClass, Decimal]
    provenance_breakdown: Mapping[Provenance, Decimal]
    confidence: RollupConfidence


__all__ = [
    "RollupConfidence",
    "RunCostRollup",
    "compose_label",
]
