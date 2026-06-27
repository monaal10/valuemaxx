"""Retraction correction tests (H8) — a retracted outcome is corrected next cycle.

When a previously-confirmed outcome flips to ``outcome_retracted`` it is removed
from the cost-per-outcome denominator. The next digest cycle must not silently
restate the metric: it emits an explicit :class:`Correction` naming the affected
outcome, the previous value, and the recomputed value.
"""

from __future__ import annotations

from decimal import Decimal

from valuemaxx.notify.correction import correction_for_retraction


def test_retraction_emits_correction() -> None:
    """A retracted outcome produces a Correction with the before/after values."""
    correction = correction_for_retraction(
        metric_name="cost_per_outcome",
        previous_value=Decimal("1.00"),
        recomputed_value=Decimal("1.25"),
        retracted_outcome_id="oe-42",
    )
    assert correction is not None
    assert correction.reason == "outcome_retracted"
    assert correction.previous_value == Decimal("1.00")
    assert correction.corrected_value == Decimal("1.25")
    assert correction.affected_outcome_id == "oe-42"


def test_no_correction_when_value_unchanged() -> None:
    """If removing the outcome did not change the metric, no correction is emitted."""
    correction = correction_for_retraction(
        metric_name="cost_per_outcome",
        previous_value=Decimal("1.00"),
        recomputed_value=Decimal("1.00"),
        retracted_outcome_id="oe-42",
    )
    assert correction is None
