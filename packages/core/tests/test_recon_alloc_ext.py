"""G1-CORE-RECON-ALLOC: ProvenanceBreakdown, AllocatedRollup, DriftAlert."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from valuemaxx.core.allocation import AllocatedLine, AllocatedRollup
from valuemaxx.core.enums import AllocationTier, BindingTier, ConfidenceLabel, Provenance
from valuemaxx.core.ids import RunId, TenantId
from valuemaxx.core.reconciliation import DriftAlert, ProvenanceBreakdown
from valuemaxx.core.rollup import RollupConfidence


def _tenant() -> TenantId:
    return TenantId(uuid4())


def test_provenance_breakdown_sums() -> None:
    """test_provenance_breakdown_sums: pct_reconciled reflects the reconciled share."""
    pb = ProvenanceBreakdown(
        reconciled_usd=Decimal("80.00"),
        provisional_usd=Decimal("15.00"),
        estimate_only_usd=Decimal("5.00"),
    )
    assert pb.total_usd == Decimal("100.00")
    assert pb.pct_reconciled == Decimal("80")


def test_provenance_breakdown_zero_total() -> None:
    pb = ProvenanceBreakdown(
        reconciled_usd=Decimal("0"),
        provisional_usd=Decimal("0"),
        estimate_only_usd=Decimal("0"),
    )
    assert pb.pct_reconciled == Decimal("0")


def _line() -> AllocatedLine:
    return AllocatedLine(
        tier=AllocationTier.DIRECT,
        label=Provenance.MEASURED,
        amount_usd=Decimal("1.00"),
        allocation_key=None,
        confidence=ConfidenceLabel.HIGH,
        sensitivity_pct=None,
        rule_version=None,
        quarantined=False,
    )


def _breakdown() -> ProvenanceBreakdown:
    return ProvenanceBreakdown(
        reconciled_usd=Decimal("1.00"),
        provisional_usd=Decimal("0"),
        estimate_only_usd=Decimal("0"),
    )


def test_allocated_rollup_carries_h7_fields() -> None:
    """test_allocated_rollup_carries_h7_fields: both H7 fields present + serialized."""
    rollup = AllocatedRollup(
        tenant_id=_tenant(),
        run_id=RunId("run-1"),
        lines=(_line(),),
        pct_unallocated=Decimal("12.5"),
        confidence=RollupConfidence.propagate([BindingTier.EXACT]),
        provenance_breakdown=_breakdown(),
    )
    assert rollup.confidence.minimum_tier is BindingTier.EXACT
    dumped = rollup.model_dump()
    assert "minimum_tier" in dumped["confidence"]
    assert "confidence_distribution" in dumped["confidence"]


def test_pct_unallocated_present() -> None:
    """test_pct_unallocated_present: the honesty anchor is a required field (§5.4)."""
    assert "pct_unallocated" in AllocatedRollup.model_fields
    rollup = AllocatedRollup(
        tenant_id=_tenant(),
        run_id=RunId("run-1"),
        lines=(_line(),),
        pct_unallocated=Decimal("0"),
        confidence=RollupConfidence.propagate([BindingTier.EXACT]),
        provenance_breakdown=_breakdown(),
    )
    assert rollup.pct_unallocated == Decimal("0")


def test_allocated_rollup_requires_tenant() -> None:
    with pytest.raises(ValidationError):
        AllocatedRollup(  # type: ignore[call-arg]
            run_id=RunId("run-1"),
            lines=(),
            pct_unallocated=Decimal("0"),
            confidence=RollupConfidence.propagate([BindingTier.EXACT]),
            provenance_breakdown=_breakdown(),
        )


def test_drift_alert_ranks_causes() -> None:
    """test_drift_alert_ranks_causes: a DriftAlert carries match_key + ranked causes."""
    alert = DriftAlert(
        match_key=("anthropic", "proj-1", "claude-opus-4-8", "output", "2026-06-27"),
        drift_pct=Decimal("14.2"),
        ranked_causes=("cache_mispricing", "negotiated_rate", "batch_discount"),
    )
    assert alert.ranked_causes[0] == "cache_mispricing"
    assert alert.drift_pct == Decimal("14.2")


def test_drift_alert_requires_at_least_one_cause() -> None:
    """A DriftAlert with no ranked causes is rejected (a drift must be explainable)."""
    with pytest.raises(ValidationError):
        DriftAlert(
            match_key=("anthropic", "proj-1", "claude-opus-4-8", "output", "2026-06-27"),
            drift_pct=Decimal("14.2"),
            ranked_causes=(),
        )
