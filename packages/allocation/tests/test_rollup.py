"""Allocation rollup — pct_unallocated honesty anchor + both H7 fields (§5.4, §3.1)."""

from __future__ import annotations

from decimal import Decimal

from _alloc_helpers import TENANT_A, make_cost_event
from valuemaxx.allocation.config import SharedCostInput, load_shared_costs
from valuemaxx.allocation.rollup import build_rollup
from valuemaxx.allocation.tier1 import Tier1Result, direct_lines
from valuemaxx.allocation.tier2 import tier2_lines
from valuemaxx.allocation.tier3 import tier3_lines
from valuemaxx.core import (
    AllocatedRollup,
    AllocationTier,
    BindingTier,
    Provenance,
    RollupConfidence,
    RunId,
)


def _tier1() -> Tier1Result:
    return direct_lines(
        [
            make_cost_event(event_id="e1", cost_usd=Decimal("60")),
            make_cost_event(event_id="e2", cost_usd=Decimal("40")),
        ]
    )


def test_rollup_carries_both_h7_fields() -> None:
    """The rollup's confidence carries minimum_tier AND confidence_distribution (H7)."""
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=(),
        tier3=tier3_lines(()),
        total_true_cost_estimate=Decimal("100"),
    )
    assert isinstance(rollup, AllocatedRollup)
    assert isinstance(rollup.confidence, RollupConfidence)
    assert rollup.confidence.minimum_tier in BindingTier
    assert rollup.confidence.confidence_distribution  # non-empty


def test_tier1_only_is_fully_allocated() -> None:
    """When measured cost equals the true-cost estimate, nothing is unallocated."""
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=(),
        tier3=tier3_lines(()),
        total_true_cost_estimate=Decimal("100"),
    )
    assert rollup.pct_unallocated == Decimal("0")


def test_pct_unallocated_surfaced_when_true_cost_exceeds_measured() -> None:
    """A true cost above the measured+allocated total surfaces as pct_unallocated."""
    # measured 100, but true cost 160 -> 60 unallocated -> 37.5%.
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=(),
        tier3=tier3_lines(()),
        total_true_cost_estimate=Decimal("160"),
    )
    assert rollup.pct_unallocated == Decimal("37.5")


def test_idle_gpu_not_smeared_into_allocated_total() -> None:
    """Idle-GPU overhead is held beside, so it does not reduce pct_unallocated."""
    fixed_yaml = """
shared_costs:
  - name: idle-gpu-pool
    amount_usd: "1000.00"
    tier: fixed_overhead
    is_idle_gpu: true
"""
    config = load_shared_costs(fixed_yaml, tenant_id=TENANT_A)
    tier3 = tier3_lines(tuple(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD)))
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=(),
        tier3=tier3,
        total_true_cost_estimate=Decimal("100"),
    )
    # idle GPU is quarantined beside; the allocated unit total is still just measured 100.
    assert rollup.pct_unallocated == Decimal("0")
    # but the idle line is still present and labeled, never dropped.
    idle_lines = [li for li in rollup.lines if li.tier is AllocationTier.FIXED_OVERHEAD]
    assert len(idle_lines) == 1
    assert idle_lines[0].quarantined is True


def test_minimum_tier_is_least_trusted_present() -> None:
    """A rollup with an allocated (Tier-2) line is headlined by the lower tier (H7)."""
    shared = SharedCostInput(
        name="vector-db",
        amount_usd=Decimal("30"),
        tier=AllocationTier.SHARED_PROPORTIONAL,
        allocation_key="requests",
        rule_version="v1",
    )
    t2 = tier2_lines(shared, {"a": Decimal("1")})
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=t2,
        tier3=tier3_lines(()),
        total_true_cost_estimate=Decimal("130"),
    )
    # measured (EXACT) + allocated (CANDIDATE) present -> minimum_tier is CANDIDATE.
    assert rollup.confidence.minimum_tier is BindingTier.CANDIDATE
    dist = rollup.confidence.confidence_distribution
    assert dist[BindingTier.EXACT] == 2  # two measured lines
    assert dist[BindingTier.CANDIDATE] == 1  # one allocated line


def test_confidence_never_raised_by_aggregation() -> None:
    """Adding a low-confidence fixed-overhead line never raises the headline tier (H7)."""
    fixed_yaml = """
shared_costs:
  - name: license
    amount_usd: "10.00"
    tier: fixed_overhead
    is_idle_gpu: false
"""
    config = load_shared_costs(fixed_yaml, tenant_id=TENANT_A)
    tier3 = tier3_lines(tuple(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD)))
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=(),
        tier3=tier3,
        total_true_cost_estimate=Decimal("110"),
    )
    # measured (EXACT) + fixed overhead (LIKELY) -> headline drops to LIKELY.
    assert rollup.confidence.minimum_tier is BindingTier.LIKELY


def test_provenance_breakdown_partitions_measured_vs_allocated() -> None:
    """The provenance breakdown reflects measured vs allocated dollars honestly."""
    shared = SharedCostInput(
        name="vector-db",
        amount_usd=Decimal("30"),
        tier=AllocationTier.SHARED_PROPORTIONAL,
        allocation_key="requests",
        rule_version="v1",
    )
    t2 = tier2_lines(shared, {"a": Decimal("1")})
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=t2,
        tier3=tier3_lines(()),
        total_true_cost_estimate=Decimal("130"),
    )
    # measured 100 reconciled vs allocated 30 -> breakdown reflects both.
    assert rollup.provenance_breakdown.reconciled_usd == Decimal("100")
    assert rollup.provenance_breakdown.estimate_only_usd == Decimal("30")


def test_zero_true_cost_is_zero_pct_unallocated() -> None:
    """A zero true-cost estimate yields 0% unallocated (no division by zero)."""
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=direct_lines([]),
        tier2=(),
        tier3=tier3_lines(()),
        total_true_cost_estimate=Decimal("0"),
    )
    assert rollup.pct_unallocated == Decimal("0")


def test_all_lines_present_in_rollup() -> None:
    """Every tier's lines appear in the rollup — none silently dropped."""
    shared = SharedCostInput(
        name="vector-db",
        amount_usd=Decimal("30"),
        tier=AllocationTier.SHARED_PROPORTIONAL,
        allocation_key="requests",
        rule_version="v1",
    )
    t2 = tier2_lines(shared, {"a": Decimal("1"), "b": Decimal("1")})
    fixed_yaml = """
shared_costs:
  - name: license
    amount_usd: "10.00"
    tier: fixed_overhead
    is_idle_gpu: false
"""
    config = load_shared_costs(fixed_yaml, tenant_id=TENANT_A)
    tier3 = tier3_lines(tuple(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD)))
    rollup = build_rollup(
        TENANT_A,
        run_id=RunId("run-1"),
        tier1=_tier1(),
        tier2=t2,
        tier3=tier3,
        total_true_cost_estimate=Decimal("140"),
    )
    measured = [li for li in rollup.lines if li.label is Provenance.MEASURED]
    allocated = [li for li in rollup.lines if li.label is Provenance.ALLOCATED]
    assert len(measured) == 2  # two tier-1 lines
    assert len(allocated) == 3  # two tier-2 + one tier-3
