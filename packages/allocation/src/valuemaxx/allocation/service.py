"""Allocation service — orchestrate the tiers and persist the result (§5.4).

:func:`allocate_run` runs the full three-tier allocation for one run:

  1. Tier-1 direct/measured lines from the run's cost events;
  2. Tier-2 shared-proportional lines for each declared ``shared_proportional`` input,
     split by the caller-supplied consumer weights;
  3. Tier-3 fixed-overhead lines (idle GPU quarantined beside the unit cost),

then assembles them into an :class:`~valuemaxx.core.AllocatedRollup` carrying
``pct_unallocated`` and both H7 confidence fields. When ``shared_costs.yaml`` is absent
(``config.is_tier1_only``) only Tier-1 is published and ``pct_unallocated`` is surfaced.

:func:`persist_rollup` writes the rollup's lines through the injected
:class:`~valuemaxx.core.AllocationRepository` (tenant-scoped); the package never imports
``valuemaxx.store`` — persistence is behind the core ABC.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.allocation.rollup import build_rollup
from valuemaxx.allocation.tier1 import direct_lines
from valuemaxx.allocation.tier2 import tier2_lines
from valuemaxx.allocation.tier3 import tier3_lines
from valuemaxx.core import AllocatedLine, AllocationTier

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from decimal import Decimal

    from valuemaxx.allocation.config import SharedCostsConfig
    from valuemaxx.core import (
        AllocatedRollup,
        AllocationRepository,
        CostEvent,
        RunId,
        TenantId,
    )


def allocate_run(
    tenant_id: TenantId,
    *,
    run_id: RunId,
    events: Iterable[CostEvent],
    config: SharedCostsConfig,
    weights: Mapping[str, Decimal],
    total_true_cost_estimate: Decimal,
) -> AllocatedRollup:
    """Run the full three-tier allocation for one run and assemble the rollup.

    Args:
        tenant_id: the tenant scope (first, structurally required).
        run_id: the run being allocated.
        events: the run's measured cost events (Tier-1).
        config: the parsed ``shared_costs.yaml`` (Tier-2/3; empty => Tier-1-only).
        weights: per-consumer weights for the Tier-2 proportional split, by key.
        total_true_cost_estimate: the run's best fully-loaded true-cost estimate, used
            to compute ``pct_unallocated``.

    Returns:
        The assembled :class:`~valuemaxx.core.AllocatedRollup`.
    """
    tier1 = direct_lines(events)

    t2_lines: list[AllocatedLine] = []
    for shared in config.inputs_for_tier(AllocationTier.SHARED_PROPORTIONAL):
        t2_lines.extend(tier2_lines(shared, weights))

    tier3 = tier3_lines(config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD))

    return build_rollup(
        tenant_id,
        run_id=run_id,
        tier1=tier1,
        tier2=tuple(t2_lines),
        tier3=tier3,
        total_true_cost_estimate=total_true_cost_estimate,
    )


def persist_rollup(
    tenant_id: TenantId,
    *,
    run_id: RunId,
    rollup: AllocatedRollup,
    repo: AllocationRepository,
) -> None:
    """Persist the rollup's allocation lines via the injected repository.

    Args:
        tenant_id: the tenant scope (first, structurally required).
        run_id: the run the lines belong to.
        rollup: the assembled allocation rollup.
        repo: the tenant-scoped allocation repository (a core ABC; never the store
            directly).
    """
    repo.upsert_lines(tenant_id, run_id, rollup.lines)


__all__ = ["allocate_run", "persist_rollup"]
