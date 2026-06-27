"""Capability I/O envelopes for the metrics package (config-AST allowlist, §3).

These are the request/response shapes the ``run_metric`` capability returns; they
are NOT domain types (the domain types stay in ``valuemaxx.core``). They carry the
core :class:`~valuemaxx.core.RollupConfidence` so every metric cell ships both H7
fields (``minimum_tier`` + ``confidence_distribution``) — a surface can never
collapse "1 exact + 50 candidate" into a clean number (the
``rollup_carries_confidence`` conformance rule). ``MetricResult`` adds the H8
re-emit flag so a retraction is never silently dropped.

This file is on the ``no_type_outside_core`` config-AST allowlist (``schemas.py``):
it shapes one capability's response envelope, it does not redefine a domain model.
"""

from __future__ import annotations

from decimal import Decimal

from valuemaxx.core.base import StrictModel
from valuemaxx.core.rollup import RollupConfidence


class MetricCell(StrictModel):
    """One computed cell of a metric (one group), carrying both H7 fields + H8 counts.

    Attributes:
        group_key: the (dimension, value) pairs identifying this group (empty for
            an ungrouped metric).
        numerator_value: the numerator measure for this group (a ``Decimal`` for
            uniformity — a count is an integral ``Decimal``).
        denominator_value: the denominator measure for this group (an integer
            count). Zero when no member qualifies (never a divide-by-zero).
        value: ``numerator / denominator`` (ROUND_HALF_EVEN), or ``None`` when the
            denominator is zero — we refuse to publish a fabricated ratio.
        confidence: the H7 conservative confidence over the contributing binding
            tiers (least-trusted headline + full distribution).
        advisory_excluded_count: confirmed outcomes excluded from a billing-grade
            denominator because their binding is advisory (candidate/likely/unbound).
        retracted_excluded_count: retracted outcomes excluded from the denominator
            and counted for the annotated re-emit (§3.1 H8).
    """

    group_key: tuple[tuple[str, str], ...]
    numerator_value: Decimal
    denominator_value: int
    value: Decimal | None
    confidence: RollupConfidence
    advisory_excluded_count: int
    retracted_excluded_count: int


class MetricResult(StrictModel):
    """The full result of running one metric: its cells + the H8 re-emit signal.

    Attributes:
        name: the metric name (echoed from the definition).
        cells: one :class:`MetricCell` per group (one cell for an ungrouped metric).
        requires_reemit: True iff any cell excluded a retracted outcome, so the
            caller re-emits the annotated metric rather than silently leaving the
            stale value (§3.1 H8).
    """

    name: str
    cells: tuple[MetricCell, ...]
    requires_reemit: bool


__all__ = ["MetricCell", "MetricResult"]
