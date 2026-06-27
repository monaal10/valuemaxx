"""ALLOC capability registration — allocated_cost_rollup (M10)."""

from __future__ import annotations

from valuemaxx.allocation import register
from valuemaxx.allocation.capabilities import (
    AllocatedCostRollupInput,
    AllocatedCostRollupOutput,
)
from valuemaxx.capabilities import Mode, Registry, Surface


def _registry() -> Registry:
    registry = Registry()
    register(registry)
    return registry


def test_register_adds_allocated_cost_rollup() -> None:
    """register projects the allocated_cost_rollup capability."""
    names = {spec.name for spec in _registry().all()}
    assert "allocated_cost_rollup" in names


def test_capability_is_request_response_on_api_mcp_cli() -> None:
    """allocated_cost_rollup is request/response on API, MCP, and CLI."""
    spec = next(s for s in _registry().all() if s.name == "allocated_cost_rollup")
    assert spec.mode is Mode.REQUEST_RESPONSE
    assert Surface.API in spec.surfaces
    assert Surface.MCP in spec.surfaces
    assert Surface.CLI in spec.surfaces


def test_handler_tier1_only_surfaces_pct_unallocated() -> None:
    """With no shared costs the handler publishes Tier-1 only + pct_unallocated."""
    spec = next(s for s in _registry().all() if s.name == "allocated_cost_rollup")
    request = AllocatedCostRollupInput(
        tenant_id="00000000-0000-0000-0000-0000000000a1",
        run_id="run-1",
        measured_costs=["60", "40"],
        shared_costs_yaml="",
        weights={},
        total_true_cost_estimate="160",
    )
    result = spec.handler(request)
    assert isinstance(result, AllocatedCostRollupOutput)
    assert result.pct_unallocated == "37.5"
    assert result.minimum_tier == "exact"  # all measured
    assert result.confidence_distribution == {"exact": 2}


def test_handler_carries_both_h7_fields() -> None:
    """The capability output carries both H7 fields (minimum_tier + distribution)."""
    spec = next(s for s in _registry().all() if s.name == "allocated_cost_rollup")
    request = AllocatedCostRollupInput(
        tenant_id="00000000-0000-0000-0000-0000000000a1",
        run_id="run-1",
        measured_costs=["100"],
        shared_costs_yaml=(
            "shared_costs:\n"
            "  - name: db\n"
            "    amount_usd: '30'\n"
            "    tier: shared_proportional\n"
            "    allocation_key: requests\n"
        ),
        weights={"a": "1"},
        total_true_cost_estimate="130",
    )
    result = spec.handler(request)
    assert isinstance(result, AllocatedCostRollupOutput)
    assert result.minimum_tier == "candidate"  # measured + allocated -> least-trusted
    assert result.confidence_distribution == {"exact": 1, "candidate": 1}


def test_handler_idle_gpu_quarantined_beside() -> None:
    """Idle GPU is quarantined beside, not smeared into the allocated unit total."""
    spec = next(s for s in _registry().all() if s.name == "allocated_cost_rollup")
    request = AllocatedCostRollupInput(
        tenant_id="00000000-0000-0000-0000-0000000000a1",
        run_id="run-1",
        measured_costs=["100"],
        shared_costs_yaml=(
            "shared_costs:\n"
            "  - name: idle\n"
            "    amount_usd: '1000'\n"
            "    tier: fixed_overhead\n"
            "    is_idle_gpu: true\n"
        ),
        weights={},
        total_true_cost_estimate="100",
    )
    result = spec.handler(request)
    assert isinstance(result, AllocatedCostRollupOutput)
    # idle GPU does not reduce pct_unallocated (held beside the unit cost).
    assert result.pct_unallocated == "0"
    assert result.quarantined_idle_usd == "1000"
