"""Tier-1 direct allocation — one MEASURED line per measured cost event (§5.4)."""

from __future__ import annotations

from decimal import Decimal

from _alloc_helpers import make_cost_event
from valuemaxx.allocation.tier1 import Tier1Result, direct_lines
from valuemaxx.core import AllocationTier, ConfidenceLabel, Provenance


def test_one_measured_line_per_event() -> None:
    """Each measured cost event becomes one Tier-1 DIRECT, measured line."""
    events = [
        make_cost_event(event_id="e1", cost_usd=Decimal("1.50")),
        make_cost_event(event_id="e2", cost_usd=Decimal("2.50")),
    ]
    result = direct_lines(events)
    assert isinstance(result, Tier1Result)
    assert len(result.lines) == 2
    for line in result.lines:
        assert line.tier is AllocationTier.DIRECT
        assert line.label is Provenance.MEASURED
        assert line.confidence is ConfidenceLabel.HIGH
        assert line.quarantined is False


def test_measured_total_sums_event_costs() -> None:
    """The measured total is the exact sum of the events' costs (Decimal)."""
    events = [
        make_cost_event(event_id="e1", cost_usd=Decimal("1.50")),
        make_cost_event(event_id="e2", cost_usd=Decimal("2.50")),
    ]
    result = direct_lines(events)
    assert result.measured_total == Decimal("4.00")


def test_ptu_event_with_none_cost_is_excluded_and_counted() -> None:
    """A PTU event (cost_usd is None) is excluded from lines but counted as unmeasured."""
    events = [
        make_cost_event(event_id="e1", cost_usd=Decimal("1.50")),
        make_cost_event(event_id="e2", cost_usd=None),  # PTU / billing-uncertain
    ]
    result = direct_lines(events)
    assert len(result.lines) == 1  # the PTU event yields no measured line
    assert result.unmeasured_event_count == 1
    assert result.measured_total == Decimal("1.50")


def test_empty_events_is_empty_result() -> None:
    """No events yields an empty Tier-1 result (zero total, zero lines)."""
    result = direct_lines([])
    assert result.lines == ()
    assert result.measured_total == Decimal("0")
    assert result.unmeasured_event_count == 0


def test_direct_lines_carry_no_allocation_key() -> None:
    """Direct (measured) lines need no allocation key — they are measured, not inferred."""
    result = direct_lines([make_cost_event(event_id="e1", cost_usd=Decimal("1"))])
    assert result.lines[0].allocation_key is None
