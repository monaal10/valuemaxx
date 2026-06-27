"""Capability projection tests — register(registry) wires run_metric.

``register`` projects the ``run_metric`` capability (request/response on
API|MCP|CLI) onto the registry; ``bind_runtime`` supplies the executor/window/
outcomes the handler needs. The capability I/O are a core ``MetricDefinition`` in
and a ``MetricResult`` out (no domain type defined outside core).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from _metrics_helpers import InMemoryCostEventRepository, InMemoryOutcomeEventRepository
from valuemaxx.capabilities import Mode, Registry, Surface
from valuemaxx.core import (
    BindingTier,
    MetricDefinition,
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    SignalClass,
    TenantId,
)
from valuemaxx.metrics import MetricRuntime, register
from valuemaxx.metrics.capabilities import MetricsNotWiredError
from valuemaxx.metrics.executor import MetricExecutor, MetricWindow
from valuemaxx.metrics.schemas import MetricResult

_TENANT = TenantId(uuid4())
_WINDOW = MetricWindow(
    start=datetime(2026, 6, 1, tzinfo=UTC),
    end=datetime(2026, 7, 1, tzinfo=UTC),
)


def _definition() -> MetricDefinition:
    return MetricDefinition(
        name="cost_per_outcome",
        numerator="total_cost_usd",
        denominator="verified_outcome_count",
        filters={},
        group_by=(),
    )


def _outcome() -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=_TENANT,
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


def _runtime() -> MetricRuntime:
    costs = InMemoryCostEventRepository()
    outcomes = InMemoryOutcomeEventRepository()
    outcomes.upsert(_TENANT, _outcome())
    executor = MetricExecutor(cost_repo=costs, outcome_repo=outcomes)
    return MetricRuntime(
        tenant_id=_TENANT,
        executor=executor,
        window=_WINDOW,
        outcomes=outcomes.list_all(_TENANT),
    )


def test_register_adds_run_metric_capability() -> None:
    """register projects exactly the run_metric capability onto the registry."""
    registry = Registry()
    register(registry)
    names = {spec.name for spec in registry.all()}
    assert names == {"run_metric"}


def test_run_metric_is_request_response_on_three_surfaces() -> None:
    """run_metric is request/response on API|MCP|CLI (per the build plan)."""
    registry = Registry()
    register(registry)
    spec = next(s for s in registry.all() if s.name == "run_metric")
    assert spec.mode is Mode.REQUEST_RESPONSE
    assert spec.surfaces == Surface.API | Surface.MCP | Surface.CLI
    assert spec.input_model is MetricDefinition
    assert spec.output_model is MetricResult


def test_handler_runs_the_metric_after_binding_runtime() -> None:
    """Once a runtime is bound, the handler validates+compiles+runs the metric."""
    from valuemaxx.metrics import bind_runtime

    registry = Registry()
    register(registry)
    bind_runtime(registry, _runtime())
    spec = next(s for s in registry.all() if s.name == "run_metric")

    result = spec.handler(_definition())
    assert isinstance(result, MetricResult)
    assert result.name == "cost_per_outcome"


def test_handler_raises_before_runtime_is_wired() -> None:
    """A handler invoked before bind_runtime raises rather than silently no-op."""
    registry = Registry()
    register(registry)
    spec = next(s for s in registry.all() if s.name == "run_metric")
    with pytest.raises(MetricsNotWiredError):
        spec.handler(_definition())


def test_bind_runtime_without_register_raises() -> None:
    """bind_runtime on a registry that never registered is an error (no holder)."""
    from valuemaxx.metrics import bind_runtime

    registry = Registry()
    with pytest.raises(MetricsNotWiredError):
        bind_runtime(registry, _runtime())
