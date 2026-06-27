"""AllocatedLine — one line of the three-tier shared-COGS allocation (§5.4).

Every line is labeled ``measured`` (DIRECT) vs ``allocated`` (SHARED/FIXED), and
the consistency rules are enforced at construction:
  - DIRECT  => label measured;
  - SHARED_PROPORTIONAL / FIXED_OVERHEAD => label allocated;
  - SHARED_PROPORTIONAL requires an allocation_key;
  - quarantined is True iff the tier is FIXED_OVERHEAD (idle GPU is reported
    beside the unit cost, never smeared in).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import model_validator

from atm_core.base import StrictModel
from atm_core.enums import AllocationTier, ConfidenceLabel, Provenance


class AllocatedLine(StrictModel):
    """One labeled allocation line carrying its key, confidence, and sensitivity."""

    tier: AllocationTier
    label: Provenance
    amount_usd: Decimal
    allocation_key: str | None
    confidence: ConfidenceLabel
    sensitivity_pct: Decimal | None
    rule_version: str | None
    quarantined: bool

    @model_validator(mode="after")
    def _tier_label_consistency(self) -> AllocatedLine:
        """Enforce the tier<->label, allocation_key, and quarantine invariants."""
        if self.tier is AllocationTier.DIRECT and self.label is not Provenance.MEASURED:
            raise ValueError("DIRECT lines must be labeled measured")
        if self.tier is not AllocationTier.DIRECT and self.label is not Provenance.ALLOCATED:
            raise ValueError("SHARED_PROPORTIONAL / FIXED_OVERHEAD lines must be labeled allocated")
        if self.tier is AllocationTier.SHARED_PROPORTIONAL and self.allocation_key is None:
            raise ValueError("SHARED_PROPORTIONAL lines require an allocation_key")
        should_quarantine = self.tier is AllocationTier.FIXED_OVERHEAD
        if self.quarantined is not should_quarantine:
            raise ValueError("quarantined must be True iff the tier is FIXED_OVERHEAD")
        return self


__all__ = ["AllocatedLine"]
