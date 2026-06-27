"""valuemaxx.notify — Slack/email digest sinks (aggregate-only, H7-labeled).

The notify surface reads aggregate rollups via the capability registry and emits
digests to Slack/email. It carries no raw content or PII (structurally forbidden on
the digest models) and never collapses the conservative H7 confidence: every metric
ships its ``minimum_tier`` + ``confidence_distribution``. Retracted outcomes are
corrected (never silently restated) on the next cycle.
"""

from __future__ import annotations

from valuemaxx.notify.builder import (
    RollupView,
    build_digest,
    build_digest_metric,
    filter_by_minimum_tier,
)
from valuemaxx.notify.correction import correction_for_retraction
from valuemaxx.notify.models import Correction, Digest, DigestMetric
from valuemaxx.notify.register import register

__all__ = [
    "Correction",
    "Digest",
    "DigestMetric",
    "RollupView",
    "build_digest",
    "build_digest_metric",
    "correction_for_retraction",
    "filter_by_minimum_tier",
    "register",
]
