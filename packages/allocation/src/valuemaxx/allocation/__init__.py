"""valuemaxx.allocation — tiered shared-COGS allocation (§5.4).

Allocation turns measured cost plus declared shared costs into a per-run, fully
labeled fully-loaded cost, with an honesty anchor so a partial picture never reads as
complete:

  * :func:`~valuemaxx.allocation.tier1.direct_lines` — Tier-1 direct/measured lines
    (one per measured event; PTU events counted, never fabricated);
  * :func:`~valuemaxx.allocation.tier2.tier2_lines` — Tier-2 shared-proportional split
    by the declared key (exact Decimal largest-remainder; every line labeled allocated);
  * :func:`~valuemaxx.allocation.tier3.tier3_lines` — Tier-3 fixed overhead, with
    idle-GPU capacity quarantined beside the unit cost (never smeared in);
  * :func:`~valuemaxx.allocation.config.load_shared_costs` — ``shared_costs.yaml`` intake
    (absent => Tier-1-only mode + ``pct_unallocated`` surfaced);
  * :func:`~valuemaxx.allocation.rollup.build_rollup` — assemble into an
    :class:`~valuemaxx.core.AllocatedRollup` carrying ``pct_unallocated`` + BOTH H7
    fields (``minimum_tier`` + ``confidence_distribution``);
  * :func:`~valuemaxx.allocation.service.allocate_run` / ``persist_rollup`` — orchestrate
    and persist through the core :class:`~valuemaxx.core.AllocationRepository` ABC.

The package depends only on ``valuemaxx.core`` ABCs/Protocols and
``valuemaxx.capabilities``; it never imports ``valuemaxx.store`` or a sibling logic
package. :func:`register` projects its capability onto the registry.
"""

from __future__ import annotations

from valuemaxx.allocation.capabilities import register
from valuemaxx.allocation.config import (
    SharedCostInput,
    SharedCostsConfig,
    load_shared_costs,
)
from valuemaxx.allocation.rollup import build_rollup
from valuemaxx.allocation.service import allocate_run, persist_rollup
from valuemaxx.allocation.tier1 import Tier1Result, direct_lines
from valuemaxx.allocation.tier2 import allocate_proportional, tier2_lines
from valuemaxx.allocation.tier3 import Tier3Result, tier3_lines

__all__ = [
    "SharedCostInput",
    "SharedCostsConfig",
    "Tier1Result",
    "Tier3Result",
    "allocate_proportional",
    "allocate_run",
    "build_rollup",
    "direct_lines",
    "load_shared_costs",
    "persist_rollup",
    "register",
    "tier2_lines",
    "tier3_lines",
]
