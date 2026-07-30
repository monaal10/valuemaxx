"""The runnable backend assembly — boot the store, wire capabilities, serve routes.

:func:`create_app` is the single composition root that turns the engine + the API
projection into a running server:

1. build the canonical capability registry via
   :func:`~valuemaxx.agent_integrability.discovery.build_default_registry`;
2. project it onto FastAPI routes via the existing
   :func:`~valuemaxx.api.app.build_app` (one route per ``Surface.API`` capability,
   tenant resolved from the API key);
3. on ASGI **startup** (a FastAPI lifespan), open the
   :class:`~valuemaxx.server.store_bridge.StoreBridge` over the configured
   ``database_url`` — this runs ``upgrade_to_head`` migrations and builds the async
   store behind synchronous repositories — then inject those repositories into the
   capability runtimes that need persistence: capture's OTLP-in (so a span lands in
   the store as a CostEvent) and the metrics executor (so ``run_metric`` reads what
   was ingested — cost rollups by model/provider/agent and cost-per-outcome, the
   agent dimension resolved through the run repo's ``run_id -> Run.agent_name`` join);
4. on ASGI **shutdown**, close the bridge so the engine is disposed on its own loop.

Deferring the store to startup keeps importing this module side-effect-free, so the
module-level :data:`app` (the ASGI entrypoint ``uvicorn valuemaxx.server.app:app``
serves) builds no database at import time.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.api.app import build_app
from valuemaxx.attribution import AttributionRuntime
from valuemaxx.attribution import bind_runtime as bind_attribution_runtime
from valuemaxx.capture import IngestRuntime, bind_ingest_runtime, default_pricebook
from valuemaxx.core.enums import Provenance
from valuemaxx.core.ids import TenantId
from valuemaxx.eval import EvalService
from valuemaxx.eval import bind_runtime as bind_eval_runtime
from valuemaxx.eval.providers import (
    AnthropicEvalProvider,
    StructuralReconstructibilityValidator,
    UrllibHttpPost,
)
from valuemaxx.metrics import MetricExecutor, MetricRuntime, MetricWindow
from valuemaxx.metrics import bind_runtime as bind_metrics_runtime
from valuemaxx.server.settings import ServerSettings
from valuemaxx.server.store_bridge import StoreBridge

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI
    from valuemaxx.capabilities import Registry


class _SystemClock:
    """The injected production clock — tz-aware UTC now (no bare datetime.now in app code)."""

    def now(self) -> datetime:
        """Return the current tz-aware UTC time."""
        return datetime.now(UTC)


# The default metrics aggregation window — effectively all of recorded time. The
# ``run_metric`` query reads every cost event in the tenant scope; a caller scopes
# tighter via the metric filters. (Per-window querying is a future capability arg.)
_WINDOW_START = datetime(1970, 1, 1, tzinfo=UTC)
_WINDOW_END = datetime(9999, 12, 31, tzinfo=UTC)

# How far back a delayed outcome may reach to claim a run by shared entity id (T4).
# 24h covers the common "the deal closed the next morning" case without letting an
# outcome bind to a week-old run it had nothing to do with. Entity-matched bindings are
# labeled `candidate` regardless, so this bounds a fallback, never a billing-grade link.
_ENTITY_BINDING_WINDOW = timedelta(hours=24)


def _first_tenant(ingest_keys: dict[str, str]) -> TenantId | None:
    """The tenant the metrics runtime is scoped to (the first configured ingest key).

    The current ``run_metric`` capability binds one tenant scope at startup (the
    metric input carries no tenant; the tenant is never read from the body). The
    store query it issues is tenant-scoped, so it returns only that tenant's cost.
    """
    for tenant in ingest_keys.values():
        return TenantId(UUID(tenant))
    return None


def _wire_runtimes(registry: Registry, bridge: StoreBridge, settings: ServerSettings) -> None:
    """Inject the store repositories into the capture + metrics capability runtimes."""
    clock = _SystemClock()
    # Price ingested spans with the curated starter book so a new user sees real dollar
    # numbers out of the box. The book is a list-price SNAPSHOT, so its computed costs are
    # ESTIMATED — never laundered to measured (the H7 axis). A span that declares its own
    # ai_margin.provenance (e.g. valuemaxx's SDK, or a gateway-reconciled cost) overrides.
    bind_ingest_runtime(
        registry,
        IngestRuntime(
            repo=bridge.cost_events,
            pricebook=default_pricebook(),
            clock=clock,
            default_provenance=Provenance.ESTIMATED,
            # Register the run as its first span arrives. The attribution cascade
            # revalidates every deterministic run id against this repo and refuses one
            # it cannot find, so without this an outcome can never bind exactly and
            # cost-per-outcome stays null.
            run_repo=bridge.runs,
        ),
    )
    # Attribution: the binding cascade that turns an inbound outcome into a
    # tier-labeled link to the run that produced it. Without this the `bind_outcome`
    # and `list_review_queue` capabilities raise AttributionNotWiredError, so an
    # outcome can never be recorded and cost-per-outcome is permanently null — the
    # product's headline metric, unreachable.
    #
    # `judge` and `semantic_window` stay None: those power the LOWEST-confidence
    # (`likely`) tier, an LLM-judged semantic match. Leaving them unset means the
    # cascade stops at the entity/time fallback rather than guessing, which is the
    # honest default — a binding we cannot make deterministically should surface for
    # human review, not be invented by a model the operator never configured.
    bind_attribution_runtime(
        registry,
        AttributionRuntime(
            run_repo=bridge.runs,
            review_queue=bridge.review_queue,
            entity_window=_ENTITY_BINDING_WINDOW,
            # Persist the bound outcome, or metrics never see it: the executor reads
            # outcomes from the store, so an unpersisted outcome leaves
            # verified_outcome_count at zero and cost-per-outcome null.
            outcome_repo=bridge.outcome_events,
        ),
    )

    # Eval: the "would a cheaper model hold this outcome" funnel. Its three seams
    # (judge, provider tokenizer, reconstructibility validator) had only test stubs, so
    # `run_eval_funnel` raised EvalNotWiredError and the model-recommendation surface
    # was permanently empty. The judge/tokenizer share one Anthropic-backed provider;
    # the CANDIDATE's key rides each request (`candidate_secret_ref`) so a user
    # evaluates with their own key and it is never persisted with the recommendation.
    eval_provider = AnthropicEvalProvider(
        http=UrllibHttpPost(), api_key=settings.eval_judge_api_key or ""
    )
    bind_eval_runtime(
        registry,
        EvalService(
            dataset_repo=bridge.eval_datasets,
            recommendation_repo=bridge.eval_recommendations,
            validator=StructuralReconstructibilityValidator(),
            judge=eval_provider,
            provider=eval_provider,
            # Grade the tenant's REAL recorded outcomes. Without this the funnel falls
            # back to its built-in sample, and a recommendation from fabricated cases
            # says nothing about the host's workload while sounding just as confident.
            outcome_repo=bridge.outcome_events,
        ),
    )

    tenant = _first_tenant(settings.resolved_ingest_keys())
    if tenant is not None:
        executor = MetricExecutor(
            cost_repo=bridge.cost_events,
            outcome_repo=bridge.outcome_events,
            run_repo=bridge.runs,
        )
        bind_metrics_runtime(
            registry,
            MetricRuntime(
                tenant_id=tenant,
                executor=executor,
                window=MetricWindow(start=_WINDOW_START, end=_WINDOW_END),
                # Resolved PER REQUEST, not snapshotted at startup. A static tuple
                # here meant every outcome recorded after boot was invisible to the
                # denominator, so cost-per-outcome stayed null no matter how cleanly
                # the outcome bound.
                outcomes=lambda: bridge.outcome_events.list_in_window(
                    tenant, _WINDOW_START, _WINDOW_END
                ),
            ),
        )


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    """Build the runnable FastAPI app: routes now; store + migrations + wiring at startup.

    Builds and projects the capability registry immediately so the routes exist, and
    registers a lifespan that opens the store bridge (running migrations), wires the
    persistence runtimes, and disposes the engine on shutdown. Pass an explicit
    ``settings`` (tests do); otherwise read the environment via
    :class:`~valuemaxx.server.settings.ServerSettings`.
    """
    resolved = settings if settings is not None else ServerSettings()
    registry = build_default_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        bridge = StoreBridge.open(resolved.database_url)
        app.state.store_bridge = bridge
        _wire_runtimes(registry, bridge, resolved)
        try:
            yield
        finally:
            bridge.close()

    app = build_app(
        registry,
        # resolved_ingest_keys() supplies a deterministic dev key when none is configured,
        # so `valuemaxx up` is usable zero-config (the same map auth + the metrics runtime
        # bind against). With real keys configured this is exactly those keys.
        api_keys=resolved.resolved_ingest_keys(),
        webhook_secret=resolved.webhook_secret_bytes(),
        lifespan=lifespan,
    )
    # The assembled registry is the composition root's affordance: it is the SAME
    # ``Registry`` the surfaces project from and the runtimes bind against, so an
    # operator/test can re-bind a capability runtime (e.g. re-point ``run_metric`` at
    # the store's outcomes) without rebuilding the app. Exposed alongside the store
    # bridge the lifespan already publishes.
    app.state.registry = registry
    return app


app = create_app()
"""The ASGI entrypoint ``uvicorn valuemaxx.server.app:app`` serves (store opens on startup)."""


__all__ = ["app", "create_app"]
