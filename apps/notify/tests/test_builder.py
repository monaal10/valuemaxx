"""Digest builder tests — aggregate-only, never collapses the H7 distribution.

The builder turns aggregate rollups (read via capabilities) into ``DigestMetric``s.
It must carry both H7 fields verbatim: a 1-exact / 50-candidate mix stays
``minimum_tier == candidate`` with the full distribution ``{exact:1, candidate:50}``
— never collapsed to a clean-looking single tier. A ``minimum_tier`` display filter
drops metrics below a floor, but each surviving metric keeps its own label.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from valuemaxx.core import BindingTier, Provenance, TenantId
from valuemaxx.core.rollup import RollupConfidence
from valuemaxx.notify.builder import (
    RollupView,
    build_digest,
    build_digest_metric,
    filter_by_minimum_tier,
)


def _mixed_confidence() -> RollupConfidence:
    return RollupConfidence(
        minimum_tier=BindingTier.CANDIDATE,
        confidence_distribution={BindingTier.EXACT: 1, BindingTier.CANDIDATE: 50},
    )


def test_builder_carries_both_h7_fields_uncollapsed() -> None:
    """1 exact + 50 candidate stays candidate with the full distribution."""
    view = RollupView(
        name="cost_per_outcome",
        value=Decimal("12.34"),
        unit="usd",
        confidence=_mixed_confidence(),
        provenance_breakdown={Provenance.MEASURED: Decimal("100")},
        pct_unallocated=None,
    )
    metric = build_digest_metric(view)
    assert metric.minimum_tier is BindingTier.CANDIDATE
    assert metric.confidence_distribution == {
        BindingTier.EXACT: 1,
        BindingTier.CANDIDATE: 50,
    }


def test_builder_produces_no_raw_fields() -> None:
    """A built metric exposes only aggregate fields (no raw content leaks)."""
    view = RollupView(
        name="m",
        value=Decimal("1"),
        unit="usd",
        confidence=_mixed_confidence(),
        provenance_breakdown={Provenance.MEASURED: Decimal("1")},
        pct_unallocated=None,
    )
    metric = build_digest_metric(view)
    field_names = set(type(metric).model_fields)
    assert not (field_names & {"raw_prompt", "raw_response", "end_user_email"})


def test_minimum_tier_filter_preserves_per_metric_labels() -> None:
    """Filtering by a tier floor drops low metrics but keeps survivors' own labels."""
    exact = build_digest_metric(
        RollupView(
            name="exact_metric",
            value=Decimal("1"),
            unit="usd",
            confidence=RollupConfidence(
                minimum_tier=BindingTier.EXACT,
                confidence_distribution={BindingTier.EXACT: 3},
            ),
            provenance_breakdown={Provenance.MEASURED: Decimal("1")},
            pct_unallocated=None,
        )
    )
    candidate = build_digest_metric(
        RollupView(
            name="candidate_metric",
            value=Decimal("2"),
            unit="usd",
            confidence=_mixed_confidence(),
            provenance_breakdown={Provenance.MEASURED: Decimal("1")},
            pct_unallocated=None,
        )
    )
    survivors = filter_by_minimum_tier((exact, candidate), floor=BindingTier.DETERMINISTIC)
    # only the exact metric clears a DETERMINISTIC floor; its own label is intact
    assert [m.name for m in survivors] == ["exact_metric"]
    assert survivors[0].minimum_tier is BindingTier.EXACT


def test_build_digest_assembles_tenant_scoped_digest() -> None:
    """build_digest produces a tenant-scoped Digest carrying the metrics + corrections."""
    tenant = TenantId(uuid4())
    view = RollupView(
        name="cost_per_outcome",
        value=Decimal("9"),
        unit="usd",
        confidence=_mixed_confidence(),
        provenance_breakdown={Provenance.MEASURED: Decimal("1")},
        pct_unallocated=None,
    )
    digest = build_digest(
        tenant_id=tenant,
        period="2026-06",
        rollups=(view,),
        corrections=(),
        generated_at="2026-06-27T00:00:00Z",
    )
    assert digest.tenant_id == tenant
    assert len(digest.metrics) == 1
    assert digest.metrics[0].minimum_tier is BindingTier.CANDIDATE
