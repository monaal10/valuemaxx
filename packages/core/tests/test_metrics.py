"""F0-CORE-1b: MetricDefinition — the typed shape (full grammar lands at G2-METRICS)."""

from __future__ import annotations

from valuemaxx.core.metrics import MetricDefinition


def test_metric_definition_round_trip() -> None:
    """T-MD-1: a MetricDefinition round-trips through JSON."""
    md = MetricDefinition(
        name="cost_per_resolution",
        numerator="total_cost_usd",
        denominator="verified_resolutions",
        filters={"agent_name": "support"},
        group_by=("agent_name",),
    )
    restored = MetricDefinition.model_validate_json(md.model_dump_json())
    assert restored == md
    assert restored.numerator == "total_cost_usd"
    assert restored.group_by == ("agent_name",)
