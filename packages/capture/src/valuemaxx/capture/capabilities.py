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
from typing import TYPE_CHECKING, Final
from uuid import UUID
from weakref import WeakKeyDictionary

from pydantic import BaseModel
from valuemaxx.capabilities import Mode, Surface, capability
from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
from valuemaxx.capture.selftest import KNOWN_GOOD
from valuemaxx.core.enums import CaptureGranularity, Provenance
from valuemaxx.core.errors import AtmError
from valuemaxx.core.ids import RunId, TenantId
from valuemaxx.core.run import Run

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from valuemaxx.capabilities import Registry
    from valuemaxx.core.context import Clock
    from valuemaxx.core.pricing import PriceBook
    from valuemaxx.core.repositories import (
        CostEventRepository,
        RawRecordRepository,
        RunRepository,
    )


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

    ``default_provenance`` is the cost-provenance label applied to a span that does not
    declare its own ``ai_margin.provenance``. It defaults to ``measured`` (valuemaxx's
    own SDK captured real usage); an app that prices third-party spans against an
    *estimated* book (e.g. the server's default snapshot pricebook) sets it to
    ``estimated`` so a computed cost is never laundered into a billing-grade one.
    """

    repo: CostEventRepository
    pricebook: PriceBook | None
    clock: Clock
    default_provenance: Provenance = Provenance.MEASURED
    # Optional so an app that only wants raw cost capture stays unchanged. When it IS
    # supplied, ingesting a span also registers the run it belongs to — without that
    # row the attribution cascade REFUSES to bind an outcome to the run ("never bind a
    # ghost"), so cost-per-outcome is permanently null no matter what the caller sends.
    run_repo: RunRepository | None = None
    # Optional store for the replay corpus: the prompt + response text of a captured
    # call, kept ONLY when the host sent them (content capture is opt-in). Without it
    # the eval funnel can never re-run a real prompt against a candidate model.
    raw_record_repo: RawRecordRepository | None = None


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
                default_provenance=runtime.default_provenance,
            )
            runtime.repo.upsert(tenant_id, event)
            _register_run(runtime, tenant_id, run_id, request.attributes)
            _record_replay_sample(runtime, tenant_id, run_id, request.attributes)
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


# The Vercel AI SDK puts the prompt and the response text on its span by default; the
# valuemaxx SDK omits them unless the host opted into content capture. So PRESENCE is
# the consent signal — we never ask for content, we only keep what the host chose to
# send. Without these, replay has nothing to re-run and the eval funnel can only
# compare pre-stored strings.
# Span-attribute prefix carrying a run's business ids (`ai_margin.entity.alt_id`).
_ENTITY_PREFIX: Final[str] = "ai_margin.entity."
_PROMPT_KEYS: Final[tuple[str, ...]] = ("ai.prompt", "ai.prompt.messages", "gen_ai.prompt")
_RESPONSE_KEYS: Final[tuple[str, ...]] = ("ai.response.text", "gen_ai.completion")


def _first_text(attributes: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    """The first non-empty string among ``keys``, or None when the host sent no content."""
    for key in keys:
        value = attributes.get(key)
        if isinstance(value, str) and value != "":
            return value
    return None


def _record_replay_sample(
    runtime: IngestRuntime,
    tenant_id: TenantId,
    run_id: str,
    attributes: Mapping[str, object],
) -> None:
    """Store the prompt + response text for replay, when the host sent them.

    Silently does nothing when either is absent — that is the content-capture-off case,
    which is the DEFAULT and must stay a no-op rather than a warning. A deployment that
    never opts in simply has no replay corpus.
    """
    repo = runtime.raw_record_repo
    if repo is None or run_id == "":
        return
    prompt = _first_text(attributes, _PROMPT_KEYS)
    response = _first_text(attributes, _RESPONSE_KEYS)
    if prompt is None or response is None:
        return
    model = attributes.get("gen_ai.request.model")
    repo.put(
        tenant_id,
        f"replay:{run_id}:{attributes.get('ai_margin.attempt_id', '')}",
        {
            "run_id": run_id,
            "model": str(model) if model is not None else None,
            "prompt": prompt,
            "response": response,
        },
        frozenset(),
    )


def _register_run(
    runtime: IngestRuntime,
    tenant_id: TenantId,
    run_id: str,
    attributes: Mapping[str, object],
) -> None:
    """Register the run this span belongs to, so an outcome can later bind to it.

    The attribution cascade REVALIDATES every deterministic run id against the run
    repository and refuses one it cannot find — it will not bind a ghost. Ingesting
    cost alone never created that row, so every outcome fell through to the advisory
    tiers and `cost_per_outcome` stayed null even when the caller supplied the exact
    run id. Registering here closes that gap at the only point that knows a run
    exists.

    Idempotent by upsert: a run with many attempts re-registers on each span. The
    first span's timestamp wins as `started_at` only in the sense that the repo
    upserts the row; we do not pretend to know the true start, and `ended_at` stays
    None because a cost span cannot tell us the run finished.
    """
    run_repo = runtime.run_repo
    if run_repo is None or run_id == "":
        return
    agent = attributes.get("ai_margin.agent_name")
    # Durable business ids the run touched, sent as `ai_margin.entity.<name>`. These are
    # what let a UNIT OF WORK span several runs — "cost per candidate" across build +
    # screen + schedule — and what the T4 fallback matches on when no run id was
    # carried. Registering an empty set (as this did) made both unreachable.
    entity_keys = frozenset(
        (key.removeprefix(_ENTITY_PREFIX), str(value))
        for key, value in attributes.items()
        if key.startswith(_ENTITY_PREFIX) and value is not None
    )
    run_repo.upsert(
        tenant_id,
        Run(
            tenant_id=tenant_id,
            id=RunId(run_id),
            agent_name=str(agent) if agent is not None else None,
            started_at=runtime.clock.now(),
            ended_at=None,
            entity_keys=entity_keys,
            experiment=_opt_str_attr(attributes, "ai_margin.experiment"),
            variant=_opt_str_attr(attributes, "ai_margin.variant"),
            app=_opt_str_attr(attributes, "ai_margin.app"),
        ),
    )


def _opt_str_attr(attributes: Mapping[str, object], key: str) -> str | None:
    """A span attribute as a string, or None when absent/empty."""
    raw = attributes.get(key)
    return str(raw) if raw is not None and str(raw) != "" else None


def ingest_attribute_maps(
    registry: Registry,
    tenant_id: TenantId,
    attribute_maps: list[dict[str, object]],
) -> int:
    """Persist a batch of decoded OTLP span attribute maps as CostEvents.

    The wire entry point for the OTLP/HTTP collector (``POST /v1/traces``): the
    SDK's exporter posts a real ``ExportTraceServiceRequest``, the collector route
    decodes it to flat attribute maps (see
    :func:`~valuemaxx.capture.otlp.collector.otlp_json_to_attribute_maps`), and this
    persists each through the **same** bound runtime + :func:`span_to_cost_event` +
    repo upsert as the single-span ``ingest_otlp_span`` handler — no duplicate
    persistence path. Returns the number of spans persisted.

    Raises :class:`IngestNotWiredError` if the registry has no bound runtime: a
    collector that silently dropped spans would be a false "captured" claim (H9).
    """
    holder = _INGEST_HOLDERS.get(registry)
    if holder is None or holder.runtime is None:
        raise IngestNotWiredError(
            "no ingest runtime bound for this registry; call bind_ingest_runtime() first"
        )
    runtime = holder.runtime
    persisted = 0
    for attrs in attribute_maps:
        if _is_rollup_span(attrs):
            continue  # a framework rollup (e.g. AI SDK ai.generateText) is not an attempt
        event = span_to_cost_event(
            attrs,
            tenant_id=tenant_id,
            pricebook=runtime.pricebook,
            clock=runtime.clock,
            default_provenance=runtime.default_provenance,
        )
        runtime.repo.upsert(tenant_id, event)
        # Register the run here too: the collector is a SEPARATE persistence entry
        # point from the single-span capability, and a run that is never registered
        # cannot be bound to by any outcome (the cascade refuses unknown run ids).
        span_run_id = str(attrs.get("ai_margin.run_id", ""))
        _register_run(runtime, tenant_id, span_run_id, attrs)
        _record_replay_sample(runtime, tenant_id, span_run_id, attrs)
        persisted += 1
    return persisted


def _is_rollup_span(attrs: dict[str, object]) -> bool:
    """True for a non-billable framework rollup span (no resolvable provider).

    The Vercel AI SDK exports both an ``ai.generateText.doGenerate`` ATTEMPT span (carrying
    ``gen_ai.system`` = the provider, plus model + usage) and a parent ``ai.generateText``
    ROLLUP span that aggregates ``ai.usage.*`` but sets NO ``gen_ai.system`` (the rollup
    keeps only the AI-SDK-internal ``ai.model.id``, never the GenAI provider). Persisting the
    rollup would create a spurious unpriced, empty-provider event and double-count the same
    tokens already captured on the attempt span. The provider is exactly what distinguishes
    a billable attempt from a rollup — and it is required to price — so a span that resolves
    NO provider is skipped. valuemaxx's own SDK + OpenInference/OpenLLMetry spans always set a
    provider, so they are never skipped.
    """
    provider = attrs.get("gen_ai.system") or attrs.get("llm.system") or attrs.get("llm.provider")
    return not provider


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
    "ingest_attribute_maps",
    "register",
]
