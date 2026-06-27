"""CLI render tests — a rollup is never printed without its minimum_tier (H7).

``render_output`` formats a capability output for the terminal. Whenever the output
is rollup-shaped — it carries an H7 confidence (a flat ``minimum_tier`` +
``confidence_distribution``, or a nested ``RollupConfidence`` in its cells) — the
rendered text MUST show the ``minimum_tier`` and the distribution, so a number can
never render bare.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from valuemaxx.cli.render import is_rollup_output, render_output
from valuemaxx.core import (
    BindingTier,
    MetricDefinition,
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    SignalClass,
    TenantId,
)
from valuemaxx.core.rollup import RollupConfidence


def test_flat_rollup_output_prints_minimum_tier() -> None:
    """A flat rollup output (allocated_cost_rollup shape) shows minimum_tier + dist."""
    from valuemaxx.allocation.capabilities import AllocatedCostRollupOutput

    output = AllocatedCostRollupOutput(
        measured_total="10.00",
        allocated_total="5.00",
        quarantined_idle_usd="0.00",
        pct_unallocated="0.00",
        minimum_tier=BindingTier.CANDIDATE.value,
        confidence_distribution={"exact": 1, "candidate": 50},
        line_count=2,
    )
    assert is_rollup_output(output)
    text = render_output(output)
    assert "minimum_tier" in text
    assert "candidate" in text
    assert "confidence_distribution" in text


def test_nested_cell_rollup_prints_minimum_tier() -> None:
    """A MetricResult (confidence nested in cells) still surfaces minimum_tier."""
    from valuemaxx.metrics.schemas import MetricCell, MetricResult

    cell = MetricCell(
        group_key=(),
        numerator_value=Decimal("10"),
        denominator_value=5,
        value=Decimal("2"),
        confidence=RollupConfidence(
            minimum_tier=BindingTier.CANDIDATE,
            confidence_distribution={BindingTier.EXACT: 1, BindingTier.CANDIDATE: 3},
        ),
        advisory_excluded_count=0,
        retracted_excluded_count=0,
    )
    result = MetricResult(name="cost_per_outcome", cells=(cell,), requires_reemit=False)
    assert is_rollup_output(result)
    text = render_output(result)
    assert "minimum_tier" in text
    assert "candidate" in text


def test_non_rollup_output_is_not_flagged_as_rollup() -> None:
    """A plain output with no confidence is not treated as a rollup."""

    def _outcome() -> OutcomeEvent:
        return OutcomeEvent(
            tenant_id=TenantId(uuid4()),
            id=OutcomeEventId(f"oe-{uuid4()}"),
            name="signup",
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            value=Decimal("1"),
            occurred_at=datetime(2026, 6, 15, tzinfo=UTC),
            binding=OutcomeBinding(run_id=None, tier=BindingTier.EXACT, bound_by="t1"),
            entity_keys=frozenset(),
            correlation_id=None,
            source="test",
            raw={},
        )

    output = _outcome()
    assert not is_rollup_output(output)
    text = render_output(output)
    assert "signup" in text


def test_model_with_direct_confidence_field_is_a_rollup() -> None:
    """A model carrying a top-level ``confidence`` field is a rollup and prints its tier."""
    from valuemaxx.core import RunCostRollup, RunId

    rollup = RunCostRollup(
        tenant_id=TenantId(uuid4()),
        run_id=RunId("run-1"),
        total_cost_usd=Decimal("3.00"),
        by_token_class={},
        provenance_breakdown={},
        confidence=RollupConfidence(
            minimum_tier=BindingTier.DETERMINISTIC,
            confidence_distribution={BindingTier.DETERMINISTIC: 2},
        ),
    )
    assert is_rollup_output(rollup)
    text = render_output(rollup)
    assert "minimum_tier" in text
    assert "deterministic" in text


def test_metric_definition_input_is_not_a_rollup() -> None:
    """A non-rollup model with no minimum_tier renders without claiming a tier."""
    definition = MetricDefinition(
        name="m",
        numerator="total_cost_usd",
        denominator="verified_outcome_count",
        filters={},
        group_by=(),
    )
    assert not is_rollup_output(definition)
