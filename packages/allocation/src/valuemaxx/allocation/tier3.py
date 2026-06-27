"""Tier-3 fixed-overhead allocation — idle GPU quarantined beside, not smeared (§5.4).

Tier-3 is non-usage fixed overhead (a platform license, an idle GPU pool). Every
Tier-3 :class:`~valuemaxx.core.AllocatedLine` is ``FIXED_OVERHEAD`` / ``allocated`` and
``quarantined`` (the core model enforces ``quarantined iff FIXED_OVERHEAD``): fixed
overhead is *reported beside* the per-unit cost, never blended into it.

Within that, **idle-GPU** capacity is treated specially (the CloudZero 75%-util
pattern): it is held out of the fully-loaded unit cost entirely (``quarantined_idle_
usd``) so paying for idle silicon never inflates the apparent cost-per-call. Non-idle
fixed overhead (a license everyone genuinely uses) does fold into the fully-loaded
unit cost (``fixed_overhead_in_unit_usd``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from valuemaxx.core import AllocatedLine, AllocationTier, ConfidenceLabel, Provenance

if TYPE_CHECKING:
    from collections.abc import Iterable

    from valuemaxx.allocation.config import SharedCostInput


@dataclass(frozen=True, slots=True)
class Tier3Result:
    """The Tier-3 (fixed-overhead) allocation outcome (NOT a domain model).

    Attributes:
        lines: one ``FIXED_OVERHEAD``/``allocated``/quarantined line per input.
        fixed_overhead_in_unit_usd: non-idle fixed overhead that folds into the
            fully-loaded unit cost.
        quarantined_idle_usd: idle-GPU overhead held out of the unit cost (reported
            beside it, never smeared in).
    """

    lines: tuple[AllocatedLine, ...]
    fixed_overhead_in_unit_usd: Decimal
    quarantined_idle_usd: Decimal


def tier3_lines(inputs: Iterable[SharedCostInput]) -> Tier3Result:
    """Build Tier-3 fixed-overhead lines, splitting idle-GPU out of the unit cost.

    Args:
        inputs: the declared ``fixed_overhead`` shared-cost inputs.

    Returns:
        A :class:`Tier3Result` with one quarantined line per input, the non-idle
        overhead that folds into the unit cost, and the idle-GPU overhead held beside.
    """
    lines: list[AllocatedLine] = []
    in_unit = Decimal(0)
    idle = Decimal(0)
    for shared in inputs:
        lines.append(
            AllocatedLine(
                tier=AllocationTier.FIXED_OVERHEAD,
                label=Provenance.ALLOCATED,
                amount_usd=shared.amount_usd,
                allocation_key=None,
                confidence=ConfidenceLabel.LOW,
                sensitivity_pct=shared.sensitivity_pct,
                rule_version=shared.rule_version,
                quarantined=True,
            )
        )
        if shared.is_idle_gpu:
            idle += shared.amount_usd
        else:
            in_unit += shared.amount_usd
    return Tier3Result(
        lines=tuple(lines),
        fixed_overhead_in_unit_usd=in_unit,
        quarantined_idle_usd=idle,
    )


__all__ = ["Tier3Result", "tier3_lines"]
