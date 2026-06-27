"""Retraction corrections (H8) — never silently restate a metric.

When a confirmed outcome is retracted it leaves the cost-per-outcome denominator,
which changes the metric. The next digest cycle emits a :class:`Correction` rather
than quietly overwriting the prior number. If removing the outcome happens not to
move the value, there is nothing to correct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from valuemaxx.notify.models import Correction

if TYPE_CHECKING:
    from decimal import Decimal


def correction_for_retraction(
    *,
    metric_name: str,
    previous_value: Decimal,
    recomputed_value: Decimal,
    retracted_outcome_id: str,
) -> Correction | None:
    """Return a :class:`Correction` for a retraction, or None if the value is unchanged.

    The correction always names the affected outcome and carries both the previous
    and the recomputed value, so a downstream reader sees exactly what moved and
    why (``reason == "outcome_retracted"``).
    """
    if previous_value == recomputed_value:
        return None
    return Correction(
        metric_name=metric_name,
        previous_value=previous_value,
        corrected_value=recomputed_value,
        reason="outcome_retracted",
        affected_outcome_id=retracted_outcome_id,
    )


__all__ = ["correction_for_retraction"]
