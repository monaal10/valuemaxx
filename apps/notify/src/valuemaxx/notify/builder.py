"""Digest builder — turns aggregate rollups into digest metrics, H7 intact.

The builder reads rollups (produced by the metrics/allocation/eval capabilities)
as a normalized :class:`RollupView` and projects each into a :class:`DigestMetric`.
It carries both H7 fields verbatim — the conservative ``minimum_tier`` and the full
``confidence_distribution`` — so a mixed-confidence aggregate (e.g. 1 exact + 50
candidate) can never be collapsed into a clean-looking single number.

``filter_by_minimum_tier`` is a *display* filter: it drops metrics whose headline
tier falls below a floor, but every surviving metric keeps its own label — the
filter never rewrites or collapses a survivor's distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from valuemaxx.core import BindingTier
from valuemaxx.notify.models import Digest, DigestMetric

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from decimal import Decimal

    from valuemaxx.core import Provenance, TenantId
    from valuemaxx.core.rollup import RollupConfidence

# Least-trusted -> most-trusted (mirrors core's tier order); the rank lets a display
# floor keep only the metrics that clear it.
_TIER_RANK: dict[BindingTier, int] = {
    BindingTier.LIKELY: 0,
    BindingTier.CANDIDATE: 1,
    BindingTier.DETERMINISTIC: 2,
    BindingTier.EXACT: 3,
}


@dataclass(frozen=True, slots=True)
class RollupView:
    """A normalized aggregate rollup the builder projects into a digest metric.

    This is the surface-agnostic shape every rollup-producing capability output is
    adapted into (it carries the H7 confidence + the provenance breakdown, never
    raw content). Keeping the builder on this view means it does not couple to any
    one capability's wire model.
    """

    name: str
    value: Decimal
    unit: str
    confidence: RollupConfidence
    provenance_breakdown: dict[Provenance, Decimal]
    pct_unallocated: Decimal | None


def build_digest_metric(view: RollupView) -> DigestMetric:
    """Project one :class:`RollupView` into a :class:`DigestMetric`, H7 intact.

    Copies ``minimum_tier`` and ``confidence_distribution`` straight through — the
    metric's own model validator re-checks the H7 consistency, so a collapsed or
    inconsistent confidence would raise here rather than ship.
    """
    return DigestMetric(
        name=view.name,
        value=view.value,
        unit=view.unit,
        minimum_tier=view.confidence.minimum_tier,
        confidence_distribution=dict(view.confidence.confidence_distribution),
        provenance_breakdown=dict(view.provenance_breakdown),
        pct_unallocated=view.pct_unallocated,
    )


def filter_by_minimum_tier(
    metrics: Iterable[DigestMetric], *, floor: BindingTier
) -> tuple[DigestMetric, ...]:
    """Keep only metrics whose headline tier clears ``floor`` (a display filter).

    Survivors are returned unchanged — each keeps its own ``minimum_tier`` and full
    ``confidence_distribution``. The filter never collapses or relabels a survivor.
    """
    floor_rank = _TIER_RANK[floor]
    return tuple(m for m in metrics if _TIER_RANK[m.minimum_tier] >= floor_rank)


def build_digest(
    *,
    tenant_id: TenantId,
    period: str,
    rollups: Sequence[RollupView],
    corrections: Sequence[object],
    generated_at: str,
) -> Digest:
    """Assemble a tenant-scoped :class:`Digest` from aggregate rollups.

    Each rollup becomes a :class:`DigestMetric` (H7 intact); the digest is
    aggregate-only and ``extra="forbid"``, so no raw content can ride along.
    """
    from valuemaxx.notify.models import Correction

    metrics = tuple(build_digest_metric(view) for view in rollups)
    typed_corrections = tuple(c for c in corrections if isinstance(c, Correction))
    return Digest(
        tenant_id=tenant_id,
        period=period,
        metrics=metrics,
        corrections=typed_corrections,
        generated_at=generated_at,
    )


__all__ = [
    "RollupView",
    "build_digest",
    "build_digest_metric",
    "filter_by_minimum_tier",
]
