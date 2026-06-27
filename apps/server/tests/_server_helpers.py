"""Shared helpers for the assembly-app e2e tests (package-unique, bare-imported §5b).

A typed view over the starlette TestClient (whose ``post`` references httpx private
aliases pyright cannot resolve), plus OTLP-span fixtures and the HMAC signing the
``ingest_otlp_span`` webhook route requires.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    import httpx
    from fastapi.testclient import TestClient

# Shared test constants (bare-imported via `_server_helpers`, never from conftest; §5b).
WEBHOOK_SECRET = b"e2e-webhook-secret"
KEY_A = "key-a"
KEY_B = "key-b"


class _HttpClient(Protocol):
    """A precisely-typed view of the (otherwise pyright-opaque) starlette TestClient."""

    def post(
        self,
        url: str,
        *,
        json: object | None = ...,
        content: bytes | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> httpx.Response: ...

    def get(self, url: str, *, headers: dict[str, str] | None = ...) -> httpx.Response: ...


def sign(secret: bytes, raw_body: bytes) -> str:
    """The HMAC-SHA256 hex signature the webhook route verifies over the raw body."""
    return hmac.new(secret, raw_body, hashlib.sha256).hexdigest()


def span_attributes(
    *,
    run_id: str,
    attempt_id: str,
    cost_usd: str,
    provider: str = "anthropic",
    model: str = "claude-opus-4-8",
) -> dict[str, object]:
    """An OTLP span attribute mapping carrying an authoritative inline cost.

    Keys are the ``ai_margin`` / ``gen_ai`` semantic-convention names the universal
    OTLP ingest path reads; an inline ``ai_margin.cost_usd`` is used as-is (a
    gateway's authoritative usage.cost), so the e2e value is deterministic.
    """
    return {
        "gen_ai.system": provider,
        "gen_ai.request.model": model,
        "gen_ai.usage.input_tokens": 100,
        "gen_ai.usage.output_tokens": 50,
        "ai_margin.run_id": run_id,
        "ai_margin.attempt_id": attempt_id,
        "ai_margin.capture_granularity": "per_attempt",
        "ai_margin.cost_usd": cost_usd,
    }


def ingest_span(
    client: TestClient,
    *,
    api_key: str,
    webhook_secret: bytes,
    attributes: dict[str, object],
) -> httpx.Response:
    """POST a signed OTLP span to the ``ingest_otlp_span`` webhook route.

    The tenant is resolved from ``api_key`` (never the body); the signature is over
    the exact raw bytes sent, mirroring how the SDK ships spans on the wire.
    """
    body = {"tenant_id": "ignored-overridden-by-key", "attributes": attributes}
    raw = json.dumps(body).encode("utf-8")
    headers = {
        "X-API-Key": api_key,
        "X-Signature": sign(webhook_secret, raw),
        "Content-Type": "application/json",
    }
    return cast("_HttpClient", client).post("/ingest_otlp_span", content=raw, headers=headers)


def run_metric(
    client: TestClient, *, api_key: str, definition: dict[str, object]
) -> httpx.Response:
    """POST a metric definition to the ``run_metric`` query route (tenant from key)."""
    return cast("_HttpClient", client).post(
        "/run_metric", json=definition, headers={"X-API-Key": api_key}
    )


def route_paths(app: object) -> set[str]:
    """The set of mounted route paths on a FastAPI app (typed access to opaque routes)."""
    routes = cast("list[object]", getattr(app, "routes", []))
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
    return paths


def total_cost_definition() -> dict[str, object]:
    """The cost-per-outcome metric: total cost over the billing-grade outcome count.

    ``total_cost_usd`` is the headline cost-per-outcome numerator, so the grammar
    requires the billing-grade ``verified_outcome_count`` denominator (advisory and
    retracted outcomes never inflate it, H8). With no outcomes bound the ratio is
    ``None``, but the cell's ``numerator_value`` is the sum of every persisted cost
    event in the tenant scope — exactly what was ingested.
    """
    return {
        "name": "cost_per_outcome",
        "numerator": "total_cost_usd",
        "denominator": "verified_outcome_count",
        "filters": {},
        "group_by": [],
    }


__all__ = [
    "KEY_A",
    "KEY_B",
    "WEBHOOK_SECRET",
    "ingest_span",
    "route_paths",
    "run_metric",
    "sign",
    "span_attributes",
    "total_cost_definition",
]
