"""Capability projection for the allocation package (M10, §3).

``register(registry)`` projects one request/response capability,
``allocated_cost_rollup``, onto the API|MCP|CLI surfaces: it runs the full three-tier
allocation for a run and returns the rollup with its honesty anchor
(``pct_unallocated``), both H7 confidence fields (``minimum_tier`` +
``confidence_distribution``), the quarantined idle-GPU total reported beside the unit
cost, and the per-line labels.

The pydantic classes below are **capability I/O contracts** (request/response
envelopes), not domain types — this file is on the ``no_type_outside_core`` config-AST
allowlist. The authoritative domain artifact (``AllocatedRollup``) lives only in
``valuemaxx.core``. Money crosses the wire as decimal *strings* so no float touches it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel
from valuemaxx.allocation.config import load_shared_costs
from valuemaxx.allocation.rollup import build_rollup
from valuemaxx.allocation.tier1 import direct_lines
from valuemaxx.allocation.tier2 import tier2_lines
from valuemaxx.allocation.tier3 import tier3_lines
from valuemaxx.core import (
    AllocationTier,
    AttemptId,
    CaptureGranularity,
    CostEvent,
    CostEventId,
    Provenance,
    ProvenanceLabel,
    RunId,
    TenantId,
    TokenVector,
)

if TYPE_CHECKING:
    from valuemaxx.allocation.tier1 import Tier1Result
    from valuemaxx.capabilities import Registry

from valuemaxx.capabilities import Mode, Surface, capability

_SURFACES = Surface.API | Surface.MCP | Surface.CLI

# A placeholder token vector for synthesising measured cost events from bare amounts at
# the capability boundary (the real CostEvent comes from capture; here we only need the
# amount for allocation).
_ZERO_TOKENS = TokenVector(
    input_uncached=0,
    cache_read=0,
    cache_write_5m=0,
    cache_write_1h=0,
    output=0,
    reasoning=0,
)


class AllocatedCostRollupInput(BaseModel):
    """Request to allocate one run's cost across the three tiers."""

    tenant_id: str
    run_id: str
    measured_costs: list[str]  # per-event measured cost (decimal strings)
    shared_costs_yaml: str  # the shared_costs.yaml text (empty => Tier-1-only)
    weights: dict[str, str]  # consumer weights for the Tier-2 split (decimal strings)
    total_true_cost_estimate: str


class AllocatedCostRollupOutput(BaseModel):
    """The allocation rollup summary with the honesty anchor + both H7 fields."""

    measured_total: str
    allocated_total: str
    quarantined_idle_usd: str
    pct_unallocated: str
    minimum_tier: str
    confidence_distribution: dict[str, int]
    line_count: int


def _synthetic_events(tenant_id: TenantId, run_id: RunId, costs: list[str]) -> list[CostEvent]:
    """Build measured cost events from bare amounts for the capability path."""
    from datetime import UTC, datetime

    events: list[CostEvent] = []
    for index, raw in enumerate(costs):
        events.append(
            CostEvent(
                tenant_id=tenant_id,
                id=CostEventId(f"{run_id}-{index}"),
                run_id=run_id,
                attempt_id=AttemptId(f"{run_id}-{index}"),
                provider="aggregate",
                model="aggregate",
                tokens=_ZERO_TOKENS,
                capture_granularity=CaptureGranularity.PER_ATTEMPT,
                provenance=ProvenanceLabel(provenance=Provenance.MEASURED),
                cost_usd=Decimal(raw),
                is_streaming=False,
                partial_recovered=False,
                billing_uncertain_abort=False,
                provenance_warnings=(),
                occurred_at=datetime.now(UTC),
            )
        )
    return events


def _allocated_cost_rollup(request: AllocatedCostRollupInput) -> AllocatedCostRollupOutput:
    """Handle ``allocated_cost_rollup``: run the three tiers and summarise the rollup."""
    tenant_id = TenantId(UUID(request.tenant_id))
    run_id = RunId(request.run_id)
    config = load_shared_costs(request.shared_costs_yaml, tenant_id=tenant_id)
    weights = {key: Decimal(value) for key, value in request.weights.items()}

    tier1: Tier1Result = direct_lines(_synthetic_events(tenant_id, run_id, request.measured_costs))
    t2 = tuple(
        line
        for shared in config.inputs_for_tier(AllocationTier.SHARED_PROPORTIONAL)
        for line in tier2_lines(shared, weights)
    )
    tier3 = tier3_lines(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD))

    rollup = build_rollup(
        tenant_id,
        run_id=run_id,
        tier1=tier1,
        tier2=t2,
        tier3=tier3,
        total_true_cost_estimate=Decimal(request.total_true_cost_estimate),
    )
    allocated_total = (
        sum((line.amount_usd for line in t2), Decimal(0)) + tier3.fixed_overhead_in_unit_usd
    )
    distribution = {
        tier.value: count
        for tier, count in rollup.confidence.confidence_distribution.items()
        if count > 0
    }
    return AllocatedCostRollupOutput(
        measured_total=_plain(tier1.measured_total),
        allocated_total=_plain(allocated_total),
        quarantined_idle_usd=_plain(tier3.quarantined_idle_usd),
        pct_unallocated=_plain(rollup.pct_unallocated),
        minimum_tier=rollup.confidence.minimum_tier.value,
        confidence_distribution=distribution,
        line_count=len(rollup.lines),
    )


def _plain(value: Decimal) -> str:
    """Render a Decimal as a plain (non-exponent, trimmed) string for the wire.

    Integral values render without a fractional part (``1000``, not ``1E+3``);
    fractional values keep their significant digits with trailing zeros trimmed
    (``37.5``). Uses ``format(..., "f")`` so no scientific notation ever leaks.
    """
    if value == value.to_integral_value():
        return str(int(value))
    trimmed = format(value, "f").rstrip("0").rstrip(".")
    return trimmed or "0"


def register(registry: Registry) -> None:
    """Register the allocation capability (M10). Called via discover_and_register."""
    registry.register(
        capability(
            name="allocated_cost_rollup",
            input_model=AllocatedCostRollupInput,
            output_model=AllocatedCostRollupOutput,
            handler=_allocated_cost_rollup,
            description=(
                "Allocate one run's fully-loaded cost across the three tiers "
                "(direct/measured, shared-proportional by declared key, fixed "
                "overhead with idle GPU quarantined beside the unit cost). Returns "
                "pct_unallocated and both H7 confidence fields; never smears idle "
                "capacity into the unit cost."
            ),
            surfaces=_SURFACES,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


__all__ = [
    "AllocatedCostRollupInput",
    "AllocatedCostRollupOutput",
    "register",
]
