"""Drift detection — flag and explain reconciliation gaps (§5.3, M3).

When the authoritative billed total for a match key diverges from the summed
estimate by more than 10%, that is not noise — it signals a systematic pricing
gap (cache mis-pricing, a negotiated rate, a batch discount, applied credits, or
tax) that should be surfaced, never silently swallowed by proration. :func:`
classify_drift` returns a :class:`~valuemaxx.core.DriftAlert` with the causes
*ranked* by how well they explain the drift's direction, or ``None`` when the gap
is within tolerance.

The ranking is advisory: an over-bill (billed > estimated) is led by
cost-increasing causes; an under-bill (billed < estimated) is led by the discount/
credit causes. Causes are never invented — they come from the fixed catalogue.
"""

from __future__ import annotations

from decimal import Decimal

from valuemaxx.core import DriftAlert

# The fixed catalogue of reconciliation drift causes (§5.3). Ranking reorders this
# list per drift direction; it never adds a cause outside the catalogue.
KNOWN_CAUSES: tuple[str, ...] = (
    "cache_mispricing",
    "negotiated_rate",
    "batch_discount",
    "credits",
    "tax",
)

# Drift beyond this magnitude (in percent) raises an alert (§5.3). The boundary is
# inclusive on the noise side: exactly 10% is still noise, strictly greater alerts.
DRIFT_THRESHOLD_PCT = Decimal("10")

# Causes most consistent with an OVER-bill (billed > estimated), best-first.
_OVERBILL_RANK: tuple[str, ...] = (
    "cache_mispricing",
    "tax",
    "negotiated_rate",
    "batch_discount",
    "credits",
)
# Causes most consistent with an UNDER-bill (billed < estimated), best-first.
_UNDERBILL_RANK: tuple[str, ...] = (
    "negotiated_rate",
    "batch_discount",
    "credits",
    "cache_mispricing",
    "tax",
)


def drift_pct(estimated: Decimal, billed: Decimal) -> Decimal:
    """The signed relative drift ``(billed - estimated) / estimated * 100``.

    A zero estimate against a non-zero invoice is reported as +/-100% (a total
    miss); zero against zero is 0% (no division).
    """
    if estimated == 0:
        return Decimal(0) if billed == 0 else Decimal(100).copy_sign(billed - estimated)
    return (billed - estimated) / estimated * Decimal(100)


def _rank_causes(drift: Decimal) -> tuple[str, ...]:
    """Order the known causes by how well they explain the drift's direction."""
    return _UNDERBILL_RANK if drift < 0 else _OVERBILL_RANK


def classify_drift(
    match_key: tuple[str, str, str, str, str],
    *,
    estimated: Decimal,
    billed: Decimal,
) -> DriftAlert | None:
    """Classify the gap between ``estimated`` and ``billed`` for a match key.

    Args:
        match_key: the (provider, project, model, token_class, day) tuple.
        estimated: the summed per-request estimate for the key (non-negative).
        billed: the authoritative billed total for the key.

    Returns:
        A :class:`~valuemaxx.core.DriftAlert` with direction-ranked causes when the
        absolute drift exceeds 10%, else ``None`` (the gap is within tolerance).

    Raises:
        ValueError: if ``estimated`` is negative.
    """
    if estimated < 0:
        raise ValueError("estimated total must be non-negative")
    drift = drift_pct(estimated, billed)
    if abs(drift) <= DRIFT_THRESHOLD_PCT:
        return None
    return DriftAlert(
        match_key=match_key,
        drift_pct=drift,
        ranked_causes=_rank_causes(drift),
    )


__all__ = ["DRIFT_THRESHOLD_PCT", "KNOWN_CAUSES", "classify_drift", "drift_pct"]
