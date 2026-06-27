"""Tier-3 fixed-overhead allocation — idle GPU quarantined beside, never smeared (§5.4)."""

from __future__ import annotations

from decimal import Decimal

from _alloc_helpers import TENANT_A
from valuemaxx.allocation.config import SharedCostInput, load_shared_costs
from valuemaxx.allocation.tier3 import Tier3Result, tier3_lines
from valuemaxx.core import AllocationTier, ConfidenceLabel, Provenance

_YAML = """
shared_costs:
  - name: idle-gpu-pool
    amount_usd: "1000.00"
    tier: fixed_overhead
    is_idle_gpu: true
    rule_version: v2
  - name: platform-license
    amount_usd: "200.00"
    tier: fixed_overhead
    is_idle_gpu: false
    rule_version: v2
"""


def _fixed_inputs() -> tuple[SharedCostInput, ...]:
    config = load_shared_costs(_YAML, tenant_id=TENANT_A)
    return tuple(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD))


def test_every_tier3_line_is_allocated_and_quarantined() -> None:
    """Tier-3 lines are FIXED_OVERHEAD / allocated and always quarantined (core invariant)."""
    result = tier3_lines(_fixed_inputs())
    assert isinstance(result, Tier3Result)
    assert len(result.lines) == 2
    for line in result.lines:
        assert line.tier is AllocationTier.FIXED_OVERHEAD
        assert line.label is Provenance.ALLOCATED
        assert line.quarantined is True
        assert line.confidence is ConfidenceLabel.LOW


def test_idle_gpu_is_quarantined_and_excluded_from_fully_loaded() -> None:
    """Idle-GPU overhead is reported beside the unit cost, excluded from fully_loaded."""
    result = tier3_lines(_fixed_inputs())
    assert result.quarantined_idle_usd == Decimal("1000.00")
    # only the non-idle platform license counts toward the fully-loaded overhead.
    assert result.fixed_overhead_in_unit_usd == Decimal("200.00")


def test_non_idle_overhead_counts_toward_unit_cost() -> None:
    """Non-idle fixed overhead (a license) is part of the fully-loaded unit cost."""
    one = """
shared_costs:
  - name: platform-license
    amount_usd: "200.00"
    tier: fixed_overhead
    is_idle_gpu: false
"""
    config = load_shared_costs(one, tenant_id=TENANT_A)
    result = tier3_lines(tuple(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD)))
    assert result.fixed_overhead_in_unit_usd == Decimal("200.00")
    assert result.quarantined_idle_usd == Decimal("0")


def test_only_idle_overhead_keeps_unit_cost_clean() -> None:
    """A pool of pure idle GPU contributes nothing to the unit cost (all quarantined)."""
    one = """
shared_costs:
  - name: idle-gpu-pool
    amount_usd: "1000.00"
    tier: fixed_overhead
    is_idle_gpu: true
"""
    config = load_shared_costs(one, tenant_id=TENANT_A)
    result = tier3_lines(tuple(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD)))
    assert result.fixed_overhead_in_unit_usd == Decimal("0")
    assert result.quarantined_idle_usd == Decimal("1000.00")


def test_empty_inputs_is_zero_result() -> None:
    """No fixed-overhead inputs yields zero lines and zero totals."""
    result = tier3_lines(())
    assert result.lines == ()
    assert result.fixed_overhead_in_unit_usd == Decimal("0")
    assert result.quarantined_idle_usd == Decimal("0")


def test_line_carries_rule_version() -> None:
    """Fixed-overhead lines carry their rule_version for auditability."""
    result = tier3_lines(_fixed_inputs())
    assert all(line.rule_version == "v2" for line in result.lines)
