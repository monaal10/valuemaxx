"""Drift detection — the >10% alert with ranked causes (§5.3, M3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from valuemaxx.core import DriftAlert
from valuemaxx.reconciliation.drift import KNOWN_CAUSES, classify_drift, drift_pct


def _key() -> tuple[str, str, str, str, str]:
    return ("anthropic", "p", "claude-sonnet-4", "output", "2026-06-27")


def test_drift_pct_is_signed_relative_difference() -> None:
    """drift_pct = (billed - estimated) / estimated * 100."""
    assert drift_pct(Decimal("100"), Decimal("120")) == Decimal("20")
    assert drift_pct(Decimal("100"), Decimal("80")) == Decimal("-20")


def test_drift_pct_zero_estimate_nonzero_billed_is_full() -> None:
    """A non-zero invoice against a zero estimate is treated as a +100% drift."""
    assert drift_pct(Decimal("0"), Decimal("5")) == Decimal("100")


def test_drift_pct_zero_estimate_zero_billed_is_zero() -> None:
    """Nothing estimated and nothing billed is zero drift, not a division error."""
    assert drift_pct(Decimal("0"), Decimal("0")) == Decimal("0")


def test_below_threshold_is_noise_returns_none() -> None:
    """A drift within +/-10% is noise — no alert."""
    assert classify_drift(_key(), estimated=Decimal("100"), billed=Decimal("109")) is None
    assert classify_drift(_key(), estimated=Decimal("100"), billed=Decimal("91")) is None


def test_exactly_ten_percent_is_noise() -> None:
    """The boundary itself (exactly 10%) is not yet an alert — strictly greater."""
    assert classify_drift(_key(), estimated=Decimal("100"), billed=Decimal("110")) is None
    assert classify_drift(_key(), estimated=Decimal("100"), billed=Decimal("90")) is None


def test_above_threshold_emits_alert_with_ranked_causes() -> None:
    """A drift beyond 10% emits a DriftAlert carrying ranked causes."""
    alert = classify_drift(_key(), estimated=Decimal("100"), billed=Decimal("130"))
    assert isinstance(alert, DriftAlert)
    assert alert.match_key == _key()
    assert alert.drift_pct == Decimal("30")
    assert alert.ranked_causes
    assert set(alert.ranked_causes) <= set(KNOWN_CAUSES)


def test_overbill_ranks_cost_increasing_causes_first() -> None:
    """When billed exceeds estimate, cost-increasing causes rank ahead of discounts."""
    alert = classify_drift(_key(), estimated=Decimal("100"), billed=Decimal("130"))
    assert alert is not None
    assert alert.ranked_causes[0] == "cache_mispricing"
    # discounts/credits explain an under-bill, so they sort to the back here.
    assert alert.ranked_causes.index("negotiated_rate") > alert.ranked_causes.index(
        "cache_mispricing"
    )


def test_underbill_ranks_discount_causes_first() -> None:
    """When billed is below estimate, negotiated rate / discounts / credits lead."""
    alert = classify_drift(_key(), estimated=Decimal("100"), billed=Decimal("70"))
    assert alert is not None
    assert alert.drift_pct == Decimal("-30")
    assert alert.ranked_causes[0] == "negotiated_rate"
    assert alert.ranked_causes.index("cache_mispricing") > 0


def test_zero_estimate_nonzero_billed_alerts() -> None:
    """An estimate of zero against any real invoice is a >10% drift alert."""
    alert = classify_drift(_key(), estimated=Decimal("0"), billed=Decimal("5"))
    assert isinstance(alert, DriftAlert)
    assert alert.drift_pct == Decimal("100")


def test_negative_estimate_raises() -> None:
    """A negative estimate is nonsensical input and is rejected."""
    with pytest.raises(ValueError, match="non-negative"):
        classify_drift(_key(), estimated=Decimal("-1"), billed=Decimal("5"))
