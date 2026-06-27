"""The FastAPI app — a thin projection of the capability registry (§3/§4).

``build_app`` builds a FastAPI app whose routes are PROJECTED from the registry: one
route per ``Surface.API`` capability, shaped by its mode (request_response /
async_job / webhook_inbound / streaming). No capability is hand-written into the
app; nothing without the API surface is reachable. The tenant is resolved from the
API key on every route and overrides the body, so a caller can only ever act on its
own tenant. Rollup responses carry both H7 fields (the capability output models
already serialize ``minimum_tier`` + ``confidence_distribution``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from valuemaxx.api.auth import ApiKeyAuthenticator
from valuemaxx.api.jobs import JobStore
from valuemaxx.api.projection import mount_capabilities

if TYPE_CHECKING:
    from starlette.types import Lifespan
    from valuemaxx.capabilities import Registry


def build_app(
    registry: Registry,
    *,
    api_keys: dict[str, str],
    webhook_secret: bytes,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Build the API app: project every ``Surface.API`` capability onto a route.

    Args:
        registry: the capability registry to project (e.g. the canonical one from
            ``valuemaxx.agent_integrability.discovery.build_default_registry``).
        api_keys: the ingest/API key -> tenant map used to resolve the tenant.
        webhook_secret: the HMAC secret for verifying ``webhook_inbound`` bodies.
        lifespan: an optional ASGI lifespan context manager run on startup/shutdown
            (the assembly app uses it to open its store + wire persistence runtimes,
            and dispose the engine on shutdown). When ``None`` there is no
            startup/shutdown behavior — the pure projection.
    """
    app = FastAPI(
        title="valuemaxx",
        description="AI margin intelligence — cost-per-outcome with confidence.",
        lifespan=lifespan,
    )
    auth = ApiKeyAuthenticator(api_keys)
    jobs = JobStore()
    mount_capabilities(
        app,
        registry,
        auth=auth,
        jobs=jobs,
        webhook_secret=webhook_secret,
    )
    return app


__all__ = ["build_app"]
