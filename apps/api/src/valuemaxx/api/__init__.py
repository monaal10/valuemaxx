"""valuemaxx.api — FastAPI projection of the capability registry.

Each ``Surface.API`` capability becomes a route shaped by its mode
(request_response -> POST; async_job -> submit + GET /jobs/{id}; webhook_inbound ->
signed receiver; streaming -> SSE). The tenant is resolved from the API key and
overrides the body, so a caller can only ever act on its own tenant. Use
:func:`build_app` to project a registry; :func:`build_default_app` projects the
canonical registry.
"""

from __future__ import annotations

from valuemaxx.api.app import build_app
from valuemaxx.api.auth import ApiKeyAuthenticator
from valuemaxx.api.errors import (
    ApiError,
    AuthError,
    JobNotFoundError,
    WebhookSignatureError,
)


def build_default_app(*, api_keys: dict[str, str], webhook_secret: bytes):  # noqa: ANN201
    """Build the API app over the canonical capability registry."""
    from valuemaxx.agent_integrability.discovery import build_default_registry

    return build_app(build_default_registry(), api_keys=api_keys, webhook_secret=webhook_secret)


__all__ = [
    "ApiError",
    "ApiKeyAuthenticator",
    "AuthError",
    "JobNotFoundError",
    "WebhookSignatureError",
    "build_app",
    "build_default_app",
]
