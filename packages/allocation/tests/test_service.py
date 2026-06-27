"""Allocation service — orchestrate tiers, persist lines, surface Tier-1-only mode (§5.4)."""

from __future__ import annotations

from decimal import Decimal

from _alloc_helpers import TENANT_A, InMemoryAllocationRepository, make_cost_event
from valuemaxx.allocation.config import load_shared_costs
from valuemaxx.allocation.service import allocate_run, persist_rollup
from valuemaxx.core import (
    AllocatedLine,
    AllocatedRollup,
    AllocationTier,
    CostEvent,
    Provenance,
    RunId,
)


def _events() -> list[CostEvent]:
    return [
        make_cost_event(event_id="e1", cost_usd=Decimal("60")),
        make_cost_event(event_id="e2", cost_usd=Decimal("40")),
    ]


def test_allocate_run_tier1_only_when_config_absent() -> None:
    """With no shared_costs.yaml, only Tier-1 measured lines are published."""
    config = load_shared_costs("", tenant_id=TENANT_A)
    rollup = allocate_run(
        TENANT_A,
        run_id=RunId("run-1"),
        events=_events(),
        config=config,
        weights={},
        total_true_cost_estimate=Decimal("160"),
    )
    assert isinstance(rollup, AllocatedRollup)
    assert all(line.label is Provenance.MEASURED for line in rollup.lines)
    # true cost 160 vs measured 100 -> 37.5% unallocated, surfaced prominently.
    assert rollup.pct_unallocated == Decimal("37.5")


def test_allocate_run_mixes_all_three_tiers() -> None:
    """A full config produces measured + allocated lines across all three tiers."""
    yaml = """
shared_costs:
  - name: vector-db
    amount_usd: "30.00"
    tier: shared_proportional
    allocation_key: requests
    rule_version: v1
  - name: idle-gpu
    amount_usd: "500.00"
    tier: fixed_overhead
    is_idle_gpu: true
  - name: license
    amount_usd: "10.00"
    tier: fixed_overhead
    is_idle_gpu: false
"""
    config = load_shared_costs(yaml, tenant_id=TENANT_A)
    rollup = allocate_run(
        TENANT_A,
        run_id=RunId("run-1"),
        events=_events(),
        config=config,
        weights={"team-a": Decimal("1"), "team-b": Decimal("1")},
        total_true_cost_estimate=Decimal("140"),
    )
    tiers = {line.tier for line in rollup.lines}
    assert tiers == {
        AllocationTier.DIRECT,
        AllocationTier.SHARED_PROPORTIONAL,
        AllocationTier.FIXED_OVERHEAD,
    }


def test_persist_rollup_writes_lines_and_reads_back() -> None:
    """The service persists lines via the repo and reads them back (intra-pkg)."""
    repo = InMemoryAllocationRepository()
    config = load_shared_costs("", tenant_id=TENANT_A)
    rollup = allocate_run(
        TENANT_A,
        run_id=RunId("run-1"),
        events=_events(),
        config=config,
        weights={},
        total_true_cost_estimate=Decimal("100"),
    )
    persist_rollup(TENANT_A, run_id=RunId("run-1"), rollup=rollup, repo=repo)
    stored = repo.list_for_run(TENANT_A, RunId("run-1"))
    assert len(stored) == len(rollup.lines)
    assert all(isinstance(line, AllocatedLine) for line in stored)


def test_persisted_lines_survive_round_trip() -> None:
    """The persisted lines are byte-identical to the rollup's lines (lossless)."""
    repo = InMemoryAllocationRepository()
    config = load_shared_costs("", tenant_id=TENANT_A)
    rollup = allocate_run(
        TENANT_A,
        run_id=RunId("run-1"),
        events=_events(),
        config=config,
        weights={},
        total_true_cost_estimate=Decimal("100"),
    )
    persist_rollup(TENANT_A, run_id=RunId("run-1"), rollup=rollup, repo=repo)
    stored = list(repo.list_for_run(TENANT_A, RunId("run-1")))
    assert tuple(stored) == rollup.lines


def test_tenant_isolation_on_persist() -> None:
    """Lines persisted for one tenant are not visible to another."""
    repo = InMemoryAllocationRepository()
    config = load_shared_costs("", tenant_id=TENANT_A)
    rollup = allocate_run(
        TENANT_A,
        run_id=RunId("run-1"),
        events=_events(),
        config=config,
        weights={},
        total_true_cost_estimate=Decimal("100"),
    )
    persist_rollup(TENANT_A, run_id=RunId("run-1"), rollup=rollup, repo=repo)
    from _alloc_helpers import TENANT_B

    assert repo.list_for_run(TENANT_B, RunId("run-1")) == []
