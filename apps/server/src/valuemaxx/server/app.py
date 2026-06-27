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
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.api.app import build_app
from valuemaxx.capture import IngestRuntime, bind_ingest_runtime
from valuemaxx.core.ids import TenantId
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
    bind_ingest_runtime(
        registry,
        IngestRuntime(repo=bridge.cost_events, pricebook=None, clock=clock),
    )
    tenant = _first_tenant(settings.ingest_keys)
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
                outcomes=(),
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
        api_keys=resolved.ingest_keys,
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
