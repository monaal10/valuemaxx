"""The injectable ingest runtime — the OTLP-in handler persists a real CostEvent.

The ``ingest_otlp_span`` capability declares the contract; the *persistence* is
wired by the app at startup via :func:`~valuemaxx.capture.capabilities.bind_ingest_runtime`,
mirroring how attribution/metrics inject their runtime (M10). Capture stays
framework-free: the runtime carries an injected synchronous
:class:`~valuemaxx.core.repositories.CostEventRepository` (a true boundary), a
``PriceBook | None``, and an injectable :class:`~valuemaxx.core.context.Clock`.

Until a runtime is bound the handler degrades to an acknowledge-only echo (it
returns the dedup key without persisting) — never a crash, never a silent claim
that a span was stored. Once bound, every accepted span lands in the repo as a
:class:`~valuemaxx.core.cost.CostEvent`, idempotent on ``(run_id, attempt_id)``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from valuemaxx.capabilities import Registry
from valuemaxx.capture.capabilities import (
    IngestNotWiredError,
    IngestOtlpSpanInput,
    IngestOtlpSpanOutput,
    IngestRuntime,
    bind_ingest_runtime,
    register,
)
from valuemaxx.capture.otlp import semconv
from valuemaxx.core.ids import TenantId

from ._fakes import RecordingCostRepo

_TENANT = TenantId(uuid4())
_AT = datetime(2026, 6, 27, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return _AT


def _span_attrs() -> dict[str, object]:
    return {
        semconv.GEN_AI_SYSTEM: "anthropic",
        semconv.GEN_AI_REQUEST_MODEL: "claude-opus-4-8",
        semconv.GEN_AI_USAGE_INPUT_TOKENS: 100,
        semconv.GEN_AI_USAGE_OUTPUT_TOKENS: 50,
        semconv.AI_MARGIN_RUN_ID: "run-x",
        semconv.AI_MARGIN_ATTEMPT_ID: "att-x",
        semconv.AI_MARGIN_CAPTURE_GRANULARITY: "per_attempt",
        semconv.AI_MARGIN_COST_USD: "0.0030",
    }


def _ingest_handler(registry: Registry):  # noqa: ANN202 — returns a capability handler
    return next(c for c in registry.all() if c.name == "ingest_otlp_span").handler


def test_bound_runtime_persists_a_cost_event() -> None:
    """test_bound_runtime_persists_a_cost_event: a bound ingest handler stores the span."""
    registry = Registry()
    register(registry)
    repo = RecordingCostRepo()
    bind_ingest_runtime(registry, IngestRuntime(repo=repo, pricebook=None, clock=_FixedClock()))

    handler = _ingest_handler(registry)
    out = handler(IngestOtlpSpanInput(tenant_id=str(_TENANT), attributes=_span_attrs()))

    assert isinstance(out, IngestOtlpSpanOutput)
    assert out.accepted is True
    assert out.run_id == "run-x"
    assert out.attempt_id == "att-x"
    assert len(repo.upserted) == 1
    event = repo.upserted[0]
    persisted = repo.list_for_run(_TENANT, event.run_id)
    assert list(persisted) == [event]
    assert event.idempotency_key == ("run-x", "att-x")
    assert event.tenant_id == _TENANT
    assert event.provider == "anthropic"
    assert str(event.cost_usd) == "0.0030"


def test_double_delivery_is_idempotent_on_the_dedup_key() -> None:
    """test_double_delivery_is_idempotent_on_the_dedup_key: replays share (run_id, attempt_id)."""
    registry = Registry()
    register(registry)
    repo = RecordingCostRepo()
    bind_ingest_runtime(registry, IngestRuntime(repo=repo, pricebook=None, clock=_FixedClock()))
    handler = _ingest_handler(registry)

    handler(IngestOtlpSpanInput(tenant_id=str(_TENANT), attributes=_span_attrs()))
    handler(IngestOtlpSpanInput(tenant_id=str(_TENANT), attributes=_span_attrs()))

    keys = {e.idempotency_key for e in repo.upserted}
    assert keys == {("run-x", "att-x")}


def test_unwired_handler_acknowledges_without_persisting() -> None:
    """test_unwired_handler_acknowledges_without_persisting: no runtime -> echo, no store."""
    registry = Registry()
    register(registry)
    handler = _ingest_handler(registry)

    out = handler(
        IngestOtlpSpanInput(
            tenant_id=str(_TENANT),
            attributes={"ai_margin.run_id": "run-h", "ai_margin.attempt_id": "att-h"},
        )
    )
    assert isinstance(out, IngestOtlpSpanOutput)
    assert out.accepted is True
    assert out.run_id == "run-h"
    assert out.attempt_id == "att-h"


def test_bind_before_register_raises() -> None:
    """test_bind_before_register_raises: binding into an unregistered registry is an error."""
    registry = Registry()
    repo = RecordingCostRepo()
    with pytest.raises(IngestNotWiredError):
        bind_ingest_runtime(registry, IngestRuntime(repo=repo, pricebook=None, clock=_FixedClock()))


def test_bound_runtime_with_a_different_registry_does_not_leak() -> None:
    """test_bound_runtime_with_a_different_registry_does_not_leak: holders are per-registry."""
    registry_a = Registry()
    register(registry_a)
    registry_b = Registry()
    register(registry_b)
    repo_a = RecordingCostRepo()
    bind_ingest_runtime(registry_a, IngestRuntime(repo=repo_a, pricebook=None, clock=_FixedClock()))

    # registry_b was never bound; its handler must NOT persist into repo_a.
    _ingest_handler(registry_b)(
        IngestOtlpSpanInput(tenant_id=str(_TENANT), attributes=_span_attrs())
    )
    assert repo_a.upserted == []
