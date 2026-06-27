"""F0-CORE-1b: AllocatedLine — tier<->label consistency (§5.4)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from valuemaxx.core.allocation import AllocatedLine
from valuemaxx.core.enums import AllocationTier, ConfidenceLabel, Provenance


def test_direct_must_be_measured() -> None:
    """T-AL-1: a DIRECT line is labeled measured; allocated is rejected."""
    line = AllocatedLine(
        tier=AllocationTier.DIRECT,
        label=Provenance.MEASURED,
        amount_usd=Decimal("1.00"),
        allocation_key=None,
        confidence=ConfidenceLabel.HIGH,
        sensitivity_pct=None,
        rule_version=None,
        quarantined=False,
    )
    assert line.label is Provenance.MEASURED
    with pytest.raises(ValidationError):
        AllocatedLine(
            tier=AllocationTier.DIRECT,
            label=Provenance.ALLOCATED,
            amount_usd=Decimal("1.00"),
            allocation_key=None,
            confidence=ConfidenceLabel.HIGH,
            sensitivity_pct=None,
            rule_version=None,
            quarantined=False,
        )


def test_shared_requires_allocation_key() -> None:
    """T-AL-2: SHARED_PROPORTIONAL requires an allocation_key and is allocated."""
    with pytest.raises(ValidationError):
        AllocatedLine(
            tier=AllocationTier.SHARED_PROPORTIONAL,
            label=Provenance.ALLOCATED,
            amount_usd=Decimal("1.00"),
            allocation_key=None,  # missing -> reject
            confidence=ConfidenceLabel.MEDIUM,
            sensitivity_pct=Decimal("5.0"),
            rule_version="v1",
            quarantined=False,
        )
    ok = AllocatedLine(
        tier=AllocationTier.SHARED_PROPORTIONAL,
        label=Provenance.ALLOCATED,
        amount_usd=Decimal("1.00"),
        allocation_key="gpu_seconds",
        confidence=ConfidenceLabel.MEDIUM,
        sensitivity_pct=Decimal("5.0"),
        rule_version="v1",
        quarantined=False,
    )
    assert ok.allocation_key == "gpu_seconds"


def test_shared_or_fixed_must_be_allocated() -> None:
    """A SHARED/FIXED line labeled measured (not allocated) is rejected."""
    with pytest.raises(ValidationError):
        AllocatedLine(
            tier=AllocationTier.SHARED_PROPORTIONAL,
            label=Provenance.MEASURED,  # wrong: shared must be allocated
            amount_usd=Decimal("1.00"),
            allocation_key="gpu_seconds",
            confidence=ConfidenceLabel.MEDIUM,
            sensitivity_pct=Decimal("5.0"),
            rule_version="v1",
            quarantined=False,
        )


def test_quarantined_iff_fixed_overhead() -> None:
    """T-AL-3: quarantined is True iff the tier is FIXED_OVERHEAD."""
    fixed = AllocatedLine(
        tier=AllocationTier.FIXED_OVERHEAD,
        label=Provenance.ALLOCATED,
        amount_usd=Decimal("9.00"),
        allocation_key=None,
        confidence=ConfidenceLabel.LOW,
        sensitivity_pct=None,
        rule_version="v1",
        quarantined=True,
    )
    assert fixed.quarantined is True
    # fixed_overhead but not quarantined -> reject
    with pytest.raises(ValidationError):
        AllocatedLine(
            tier=AllocationTier.FIXED_OVERHEAD,
            label=Provenance.ALLOCATED,
            amount_usd=Decimal("9.00"),
            allocation_key=None,
            confidence=ConfidenceLabel.LOW,
            sensitivity_pct=None,
            rule_version="v1",
            quarantined=False,
        )
    # direct but quarantined -> reject
    with pytest.raises(ValidationError):
        AllocatedLine(
            tier=AllocationTier.DIRECT,
            label=Provenance.MEASURED,
            amount_usd=Decimal("1.00"),
            allocation_key=None,
            confidence=ConfidenceLabel.HIGH,
            sensitivity_pct=None,
            rule_version=None,
            quarantined=True,
        )
