"""ATTR-4 — capability registration + the intra-package review-queue persistence test.

``register(registry)`` projects the attribution package's two capabilities
(``bind_outcome``, ``list_review_queue``) onto the registry, each declaring the
API|MCP|CLI surfaces in request/response mode. Their I/O are ``valuemaxx.core``
domain models (no domain type is defined outside core).

The handlers are wired to a runtime :class:`~valuemaxx.attribution.cascade.Cascade`
and :class:`~valuemaxx.core.ReviewQueue` by the app at startup via
:func:`~valuemaxx.attribution.capabilities.bind_runtime`; before wiring they raise
a clear typed error rather than silently no-op.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from _attribution_helpers import (
    TENANT_A,
    InMemoryReviewQueue,
    InMemoryRunRepository,
    make_run,
    utc,
)
from valuemaxx.attribution import register
from valuemaxx.attribution.capabilities import AttributionRuntime, bind_runtime
from valuemaxx.capabilities import Mode, Registry, Surface
from valuemaxx.core import (
    AtmError,
    AttributionResult,
    BindingTier,
    OutcomeBinding,
    OutcomeEvent,
    OutcomeEventId,
    RunId,
    SignalClass,
)

_OCCURRED = utc(2026, 1, 1, 12, 0)


def _registry() -> Registry:
    registry = Registry()
    register(registry)
    return registry


def _outcome() -> OutcomeEvent:
    return OutcomeEvent(
        tenant_id=TENANT_A,
        id=OutcomeEventId("oc-1"),
        name="deal_closed",
        signal_class=SignalClass.OUTCOME_CONFIRMED,
        value=Decimal("100.00"),
        occurred_at=_OCCURRED,
        binding=OutcomeBinding(run_id=None, tier=None, bound_by=None),
        entity_keys=frozenset({("customer_id", "c-1")}),
        correlation_id=None,
        source="crm",
        raw={},
    )


def _runtime() -> AttributionRuntime:
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(run_id="run-1", started_at=_OCCURRED, entity_keys=frozenset()),
    )
    queue = InMemoryReviewQueue()
    return AttributionRuntime(run_repo=repo, review_queue=queue, entity_window=timedelta(hours=6))


def test_register_adds_both_capabilities() -> None:
    """register projects exactly the two attribution capabilities."""
    names = {spec.name for spec in _registry().all()}
    assert {"bind_outcome", "list_review_queue"} <= names


def test_capabilities_declare_api_mcp_cli_request_response() -> None:
    """Both capabilities are request/response on API, MCP, and CLI."""
    specs = {spec.name: spec for spec in _registry().all()}
    for name in ("bind_outcome", "list_review_queue"):
        spec = specs[name]
        assert spec.mode is Mode.REQUEST_RESPONSE
        assert Surface.API in spec.surfaces
        assert Surface.MCP in spec.surfaces
        assert Surface.CLI in spec.surfaces


def test_bind_outcome_io_are_core_models() -> None:
    """bind_outcome's I/O are core domain models (no type defined outside core)."""
    spec = next(s for s in _registry().all() if s.name == "bind_outcome")
    assert spec.input_model is OutcomeEvent
    assert spec.output_model is AttributionResult


def test_handlers_raise_before_runtime_is_bound() -> None:
    """An unwired handler raises a typed error rather than silently no-op."""
    spec = next(s for s in _registry().all() if s.name == "bind_outcome")
    with pytest.raises(AtmError):
        spec.handler(_outcome())


def test_bind_outcome_handler_binds_via_cascade_when_wired() -> None:
    """Once wired, the bind_outcome handler runs the cascade and returns a result."""
    registry = _registry()
    bind_runtime(registry, _runtime())
    spec = next(s for s in registry.all() if s.name == "bind_outcome")
    result = spec.handler(_outcome())
    assert isinstance(result, AttributionResult)
    # The seeded entity-less run is not an entity match; with no deterministic
    # signal supplied via the capability path, the outcome is unbound + reviewable.
    assert result.review_required is True


def test_bind_persists_review_via_queue_stub() -> None:
    """A reviewable bind is persisted to the tenant-scoped review queue (intra-pkg)."""
    runtime = _runtime()
    registry = _registry()
    bind_runtime(registry, runtime)
    spec = next(s for s in registry.all() if s.name == "bind_outcome")
    result = spec.handler(_outcome())
    pending = runtime.review_queue.list_pending(TENANT_A)
    assert pending == [result]


def test_candidate_bind_through_capability_is_never_billing_grade() -> None:
    """A candidate bind routed through the capability handler is never billing-grade."""
    repo = InMemoryRunRepository()
    repo.upsert(
        TENANT_A,
        make_run(
            run_id="entity-run",
            started_at=_OCCURRED,
            entity_keys=frozenset({("customer_id", "c-1")}),
        ),
    )
    runtime = AttributionRuntime(
        run_repo=repo, review_queue=InMemoryReviewQueue(), entity_window=timedelta(hours=6)
    )
    registry = _registry()
    bind_runtime(registry, runtime)
    spec = next(s for s in registry.all() if s.name == "bind_outcome")
    result = spec.handler(_outcome())
    assert isinstance(result, AttributionResult)
    assert result.tier is BindingTier.CANDIDATE
    assert result.is_billing_grade is False
    assert result.review_required is True


def test_list_review_queue_returns_pending() -> None:
    """list_review_queue surfaces the pending review items for the outcome's tenant."""
    runtime = _runtime()
    registry = _registry()
    bind_runtime(registry, runtime)
    bind_spec = next(s for s in registry.all() if s.name == "bind_outcome")
    bound = bind_spec.handler(_outcome())
    assert isinstance(bound, AttributionResult)
    list_spec = next(s for s in registry.all() if s.name == "list_review_queue")
    # The list capability is tenant-scoped via its input outcome's tenant id.
    listed = list_spec.handler(_outcome())
    assert isinstance(listed, AttributionResult)
    assert listed.tenant_id == TENANT_A
    assert listed.outcome_id == bound.outcome_id


def test_unknown_run_id_type_safety() -> None:
    """RunId round-trips as a plain string through the core model (sanity)."""
    assert RunId("x") == "x"
