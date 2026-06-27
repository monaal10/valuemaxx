"""Shared digest-line formatting for the sinks (H7: never a bare number).

Renders one :class:`~valuemaxx.notify.models.DigestMetric` as a single text line
showing the value, unit, and the conservative ``minimum_tier`` label plus the full
confidence distribution. Used by both the Slack and email sinks so the H7 rule is
enforced in exactly one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from valuemaxx.notify.models import Correction, Digest, DigestMetric


def format_metric_line(metric: DigestMetric) -> str:
    """One digest line: ``name: value unit [tier=<minimum_tier> dist=<...>]``."""
    dist = ", ".join(
        f"{tier.value}:{count}"
        for tier, count in sorted(
            metric.confidence_distribution.items(), key=lambda item: item[0].value
        )
    )
    return (
        f"{metric.name}: {metric.value} {metric.unit} "
        f"[tier={metric.minimum_tier.value} dist={{{dist}}}]"
    )


def format_correction_line(correction: Correction) -> str:
    """One correction line naming the retracted outcome and the before/after values."""
    return (
        f"CORRECTION ({correction.reason}) {correction.metric_name}: "
        f"{correction.previous_value} -> {correction.corrected_value} "
        f"(outcome {correction.affected_outcome_id})"
    )


def format_digest_lines(digest: Digest) -> list[str]:
    """Every metric and correction line for a digest, header first."""
    lines = [f"AI margin digest — {digest.period}"]
    lines.extend(format_metric_line(metric) for metric in digest.metrics)
    lines.extend(format_correction_line(c) for c in digest.corrections)
    return lines


__all__ = ["format_correction_line", "format_digest_lines", "format_metric_line"]
