"""RECON capability registration — reconcile_day + cost_breakdown (M10)."""

from __future__ import annotations

from decimal import Decimal

from valuemaxx.capabilities import Mode, Registry, Surface
from valuemaxx.reconciliation import register
from valuemaxx.reconciliation.capabilities import (
    CostBreakdownInput,
    CostBreakdownOutput,
    ReconcileDayInput,
    ReconcileDayOutput,
)


def _registry() -> Registry:
    registry = Registry()
    register(registry)
    return registry


def test_register_adds_both_capabilities() -> None:
    """register projects exactly the two reconciliation capabilities."""
    names = {spec.name for spec in _registry().all()}
    assert {"reconcile_day", "cost_breakdown"} <= names


def test_capabilities_are_request_response_on_api_mcp_cli() -> None:
    """Both capabilities are request/response on API, MCP, and CLI."""
    specs = {spec.name: spec for spec in _registry().all()}
    for name in ("reconcile_day", "cost_breakdown"):
        spec = specs[name]
        assert spec.mode is Mode.REQUEST_RESPONSE
        assert Surface.API in spec.surfaces
        assert Surface.MCP in spec.surfaces
        assert Surface.CLI in spec.surfaces
        assert Surface.NOTIFY not in spec.surfaces


def test_reconcile_day_handler_returns_summary() -> None:
    """The reconcile_day handler reconciles its estimates additively and summarises."""
    spec = next(s for s in _registry().all() if s.name == "reconcile_day")
    request = ReconcileDayInput(
        tenant_id="00000000-0000-0000-0000-0000000000a1",
        day="2026-06-27",
        match_key=["anthropic", "p", "claude-sonnet-4", "output", "2026-06-27"],
        estimates={"a": "10", "b": "30"},
        billed_total="60",
    )
    result = spec.handler(request)
    assert isinstance(result, ReconcileDayOutput)
    assert result.billed_total == "60"
    assert result.proration_factor == "1.5"
    # the per-request reconciled values sum to the billed total exactly.
    reconciled = [Decimal(v) for v in result.reconciled_by_request.values()]
    assert sum(reconciled, Decimal(0)) == Decimal("60")


def test_reconcile_day_surfaces_drift() -> None:
    """A >10% drift is surfaced on the capability output, never hidden."""
    spec = next(s for s in _registry().all() if s.name == "reconcile_day")
    request = ReconcileDayInput(
        tenant_id="00000000-0000-0000-0000-0000000000a1",
        day="2026-06-27",
        match_key=["anthropic", "p", "m", "output", "2026-06-27"],
        estimates={"a": "100"},
        billed_total="130",
    )
    result = spec.handler(request)
    assert isinstance(result, ReconcileDayOutput)
    assert Decimal(result.drift_pct) == Decimal("30")
    assert result.drift_causes  # ranked causes present


def test_cost_breakdown_handler_partitions_states() -> None:
    """The cost_breakdown handler returns the mixed-state breakdown summing to total."""
    spec = next(s for s in _registry().all() if s.name == "cost_breakdown")
    request = CostBreakdownInput(
        tenant_id="00000000-0000-0000-0000-0000000000a1",
        reconciled_usd="100",
        provisional_usd="30",
        estimate_only_usd="20",
    )
    result = spec.handler(request)
    assert isinstance(result, CostBreakdownOutput)
    assert result.total_usd == "150"
    assert result.reconciled_usd == "100"


def test_io_models_are_capability_envelopes() -> None:
    """The capability I/O are envelope models declared in capabilities.py (allowlisted)."""
    spec = next(s for s in _registry().all() if s.name == "reconcile_day")
    assert spec.input_model is ReconcileDayInput
    assert spec.output_model is ReconcileDayOutput
