"""System-owned confidence scoring for the binding cascade (ATTR-0).

The tier -> confidence-label mapping is system-owned and has no user setter — a
customer can never relabel an inferred match as high confidence (§3.1).
"""

from __future__ import annotations

from valuemaxx.attribution.confidence.scoring import label_for

__all__ = ["label_for"]
