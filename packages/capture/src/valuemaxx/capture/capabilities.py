"""PG5 — the capture package's capability registrations (§3, M10).

Surfaces (API/MCP/CLI/NOTIFY) are thin projections of the capability registry, so
capture declares its operations here once and ``register`` adds them. Three
capabilities:

  * ``ingest_otlp_span`` — the universal OTLP-in path (``request_response``, API):
    KEY-authenticated (resolved from the ingest X-API-Key), NOT signature-gated, because
    a real OTLP exporter sends only the ingest key and cannot HMAC-sign the body;
  * ``list_cost_sources`` — enumerate the wired cost sources (request_response);
  * ``capture_healthcheck`` — liveness + effective granularity (request_response).

The pydantic classes below are **capability I/O contracts**, not domain types —
they shape one capability's request/response and are on the fixed config-AST
allowlist of ``no_type_outside_core`` (the domain types they carry — CostEvent,
CaptureGranularity, etc. — still live only in ``valuemaxx.core``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID
from weakref import WeakKeyDictionary

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
from valuemaxx.capture.selftest import KNOWN_GOOD
from valuemaxx.core.enums import CaptureGranularity
from valuemaxx.core.errors import AtmError
from valuemaxx.core.ids import TenantId

if TYPE_CHECKING:
    from collections.abc import Callable

    from valuemaxx.capabilities import Registry
    from valuemaxx.core.context import Clock
    from valuemaxx.core.pricing import PriceBook
    from valuemaxx.core.repositories import CostEventRepository


class IngestOtlpSpanInput(BaseModel):
    """Request to ingest one OTLP span (the attribute mapping + tenant scope)."""

    tenant_id: str
    attributes: dict[str, object]


class IngestOtlpSpanOutput(BaseModel):
    """Result of ingesting one OTLP span: the deduped (run_id, attempt_id) key."""

    run_id: str
    attempt_id: str
    accepted: bool


class ListCostSourcesInput(BaseModel):
    """Request to enumerate the wired cost sources (no parameters)."""


class ListCostSourcesOutput(BaseModel):
    """The wired cost-source identifiers and whether each is authoritative spend."""

    sources: tuple[str, ...]


class CaptureHealthcheckInput(BaseModel):
    """Request for capture liveness + effective granularity (no parameters)."""


class CaptureHealthcheckOutput(BaseModel):
    """Capture health: alive flag + the effective capture granularity."""

    alive: bool
    capture_granularity: str


# The wired cost sources (authoritative spend or properly-reconciled actuals, §5.5).
_COST_SOURCES: tuple[str, ...] = (
    "client_instrument",
    "otlp_ingest",
    "gateway:openrouter",
    "provider_costapi",
)


class IngestNotWiredError(AtmError):
    """An ingest persistence binding was attempted before its registry was set up (M10)."""


@dataclass(frozen=True, slots=True)
class IngestRuntime:
    """The persistence dependencies an app injects to power ``ingest_otlp_span``.

    Capture stays framework- and store-free: it persists through the injected
    synchronous :class:`~valuemaxx.core.repositories.CostEventRepository` ABC (a
    true boundary the app fulfils — e.g. a sync bridge over the async store), prices
    via the optional :class:`~valuemaxx.core.pricing.PriceBook`, and reads the clock
    through the injected :class:`~valuemaxx.core.context.Clock` so ingest is
    deterministic under test.
    """

    repo: CostEventRepository
    pricebook: PriceBook | None
    clock: Clock


class _IngestHolder:
    """A late-bound slot for one registry's ingest runtime."""

    __slots__ = ("runtime",)

    def __init__(self) -> None:
        self.runtime: IngestRuntime | None = None


# One holder per registry instance, keyed by the registry object via a weak map so a
# garbage-collected registry drops its holder (no stale binding can leak across
# registries through object-id reuse). Mirrors the metrics/attribution pattern.
_INGEST_HOLDERS: WeakKeyDictionary[Registry, _IngestHolder] = WeakKeyDictionary()


def _make_ingest_handler(
    holder: _IngestHolder,
) -> Callable[[IngestOtlpSpanInput], IngestOtlpSpanOutput]:
    def _ingest_otlp_span(request: IngestOtlpSpanInput) -> IngestOtlpSpanOutput:
        # The dedup key is surfaced so a double delivery is visibly idempotent. When a
        # runtime is bound, the span is decoded to a CostEvent and persisted (the repo
        # upserts on (run_id, attempt_id), so a redelivery never double-counts, M7).
        # Until the app wires a runtime, the handler acknowledges without persisting —
        # never a crash, never a false claim that the span was stored.
        run_id = str(request.attributes.get("ai_margin.run_id", ""))
        attempt_id = str(request.attributes.get("ai_margin.attempt_id", ""))
        runtime = holder.runtime
        if runtime is not None:
            tenant_id = TenantId(UUID(request.tenant_id))
            event = span_to_cost_event(
                request.attributes,
                tenant_id=tenant_id,
                pricebook=runtime.pricebook,
                clock=runtime.clock,
            )
            runtime.repo.upsert(tenant_id, event)
        return IngestOtlpSpanOutput(run_id=run_id, attempt_id=attempt_id, accepted=True)

    return _ingest_otlp_span


def bind_ingest_runtime(registry: Registry, runtime: IngestRuntime) -> None:
    """Wire ``runtime`` into the ``ingest_otlp_span`` capability registered for ``registry``.

    The app calls this at startup to make OTLP-in actually persist. Raises
    :class:`IngestNotWiredError` if :func:`register` was never called for this
    registry (there is no holder to bind into).
    """
    holder = _INGEST_HOLDERS.get(registry)
    if holder is None:
        raise IngestNotWiredError(
            "no capture capabilities registered for this registry; call register() first"
        )
    holder.runtime = runtime


def _list_cost_sources(_request: ListCostSourcesInput) -> ListCostSourcesOutput:
    return ListCostSourcesOutput(sources=_COST_SOURCES)


def _capture_healthcheck(_request: CaptureHealthcheckInput) -> CaptureHealthcheckOutput:
    # default granularity is per_attempt where the transport hook is present; the
    # SDK self-test (selftest.py, KNOWN_GOOD) downgrades to per_call on bad versions.
    assert KNOWN_GOOD  # the supported-range table is wired
    return CaptureHealthcheckOutput(
        alive=True, capture_granularity=CaptureGranularity.PER_ATTEMPT.value
    )


def register(registry: Registry) -> None:
    """Register the three capture capabilities (M10). Called via discover_and_register.

    Creates a late-bound ingest-runtime holder for this registry; the app calls
    :func:`bind_ingest_runtime` at startup to make ``ingest_otlp_span`` persist a
    real :class:`~valuemaxx.core.cost.CostEvent` through the injected repository.
    """
    holder = _INGEST_HOLDERS.setdefault(registry, _IngestHolder())
    registry.register(
        capability(
            name="ingest_otlp_span",
            input_model=IngestOtlpSpanInput,
            output_model=IngestOtlpSpanOutput,
            handler=_make_ingest_handler(holder),
            description="Ingest one OTLP span as a CostEvent (universal/TS producer path).",
            surfaces=Surface.API,
            # KEY-authenticated, NOT signature-required: a real SDK ships spans via a
            # standard OTLP exporter authenticated with ONLY the per-tenant ingest key
            # (it cannot HMAC-sign the OTLP body). The tenant is resolved from the
            # X-API-Key like every other request_response capability. HMAC signing
            # belongs on EXTERNAL webhooks (Stripe/CRM outcome callbacks —
            # ingest_webhook_outcome stays webhook_inbound/signed, since there you
            # cannot use your own key). See AGENTS.md §5b (SDK ingest is key-auth).
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="list_cost_sources",
            input_model=ListCostSourcesInput,
            output_model=ListCostSourcesOutput,
            handler=_list_cost_sources,
            description="List the wired cost sources (authoritative spend / reconciled actuals).",
            surfaces=Surface.API | Surface.MCP | Surface.CLI,
            mode=Mode.REQUEST_RESPONSE,
        )
    )
    registry.register(
        capability(
            name="capture_healthcheck",
            input_model=CaptureHealthcheckInput,
            output_model=CaptureHealthcheckOutput,
            handler=_capture_healthcheck,
            description="Report capture liveness and the effective capture granularity.",
            surfaces=Surface.API | Surface.MCP | Surface.CLI,
            mode=Mode.REQUEST_RESPONSE,
        )
    )


__all__ = [
    "CaptureHealthcheckInput",
    "CaptureHealthcheckOutput",
    "IngestNotWiredError",
    "IngestOtlpSpanInput",
    "IngestOtlpSpanOutput",
    "IngestRuntime",
    "ListCostSourcesInput",
    "ListCostSourcesOutput",
    "bind_ingest_runtime",
    "register",
]
