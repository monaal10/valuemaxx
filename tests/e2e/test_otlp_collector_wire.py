"""Regression e2e: the REAL OTLP/HTTP wire path (POST /v1/traces) lands a CostEvent.

The live vibechk integration test caught the decisive gap: the TS SDK's
``@opentelemetry/exporter-trace-otlp-http`` posts a standard OTLP-JSON
``ExportTraceServiceRequest`` to ``<endpoint>/v1/traces`` with the per-tenant key in
the ``x-valuemaxx-ingest-key`` header — but the backend had **no /v1/traces route**
(404) and only a pre-shaped ``{tenant_id, attributes}`` JSON route reading
``X-API-Key`` (401). The two halves of the shipped product could not talk: every
prior test hit ``/ingest_otlp_span`` directly and never exercised the real exporter
wire format.

This test drives the genuine wire shape end to end with NO pre-shaping and NO
``X-API-Key``:

1. The real :func:`~valuemaxx.server.app.create_app` boots over a fresh temp SQLite
   DB through Starlette's ``TestClient`` (migrations run; the capture runtime wires).
2. A POST of a real OTLP-JSON ``ExportTraceServiceRequest`` (intValue wire-encoded as
   a *string*, exactly as the exporter emits) hits ``POST /v1/traces`` with ONLY the
   ``x-valuemaxx-ingest-key`` header — the exact request a real OTLP exporter sends.
3. The CostEvent lands under the right tenant with the right cost, proven by querying
   it back through ``/run_metric`` — never by inspecting internals.

If ``/v1/traces`` regresses (route removed, header renamed, intValue decoded as a
string so tokens read 0), this fails — the integration gap cannot recur silently.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from valuemaxx.server.app import create_app
from valuemaxx.server.settings import ServerSettings

if TYPE_CHECKING:
    from collections.abc import Iterator

    import httpx

WEBHOOK_SECRET = b"otlp-collector-secret"
INGEST_KEY = "user-ingest-key"
_COST_USD = Decimal("0.0125")


class _HttpClient(Protocol):
    """A precisely-typed view of the otherwise pyright-opaque starlette TestClient."""

    def post(
        self,
        url: str,
        *,
        json: object | None = ...,
        content: bytes | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> httpx.Response: ...


def _otlp_export_request(*, run_id: str) -> dict[str, object]:
    """One real OTLP-JSON ExportTraceServiceRequest (the exact exporter wire shape).

    Note ``intValue`` is wire-encoded as a STRING — the precise trap the collector
    must decode back to a native int, else the token reader sees 0 and cost is wrong.
    """
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "vibechk"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "valuemaxx"},
                        "spans": [
                            {
                                "name": "ai.generateText",
                                "attributes": [
                                    {
                                        "key": "gen_ai.system",
                                        "value": {"stringValue": "anthropic"},
                                    },
                                    {
                                        "key": "gen_ai.request.model",
                                        "value": {"stringValue": "claude-3-5-haiku"},
                                    },
                                    {
                                        "key": "gen_ai.usage.input_tokens",
                                        "value": {"intValue": "1000"},
                                    },
                                    {
                                        "key": "gen_ai.usage.output_tokens",
                                        "value": {"intValue": "250"},
                                    },
                                    {
                                        "key": "ai_margin.run_id",
                                        "value": {"stringValue": run_id},
                                    },
                                    {
                                        "key": "ai_margin.attempt_id",
                                        "value": {"stringValue": "attempt-1"},
                                    },
                                    {
                                        "key": "ai_margin.cost_usd",
                                        "value": {"stringValue": str(_COST_USD)},
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _run_total_cost_metric(client: TestClient, *, api_key: str) -> httpx.Response:
    """POST the cost-per-outcome metric to ``/run_metric`` (tenant resolved from key)."""
    definition: dict[str, object] = {
        "name": "cost_per_outcome",
        "numerator": "total_cost_usd",
        "denominator": "verified_outcome_count",
        "filters": {},
        "group_by": [],
    }
    return cast("_HttpClient", client).post(
        "/run_metric", json=definition, headers={"X-API-Key": api_key}
    )


@pytest.fixture
def tenant() -> str:
    return str(uuid4())


@pytest.fixture
def settings(tmp_path: object, tenant: str) -> ServerSettings:
    db_path = Path(str(tmp_path)) / "otlp-collector.db"
    return ServerSettings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        ingest_keys={INGEST_KEY: tenant},
        webhook_secret=WEBHOOK_SECRET.decode("utf-8"),
    )


@pytest.fixture
def client(settings: ServerSettings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def test_real_otlp_wire_lands_cost_event(client: TestClient) -> None:
    """A real OTLP-JSON export to /v1/traces (key-auth header) persists a queryable cost."""
    body = _otlp_export_request(run_id="vibechk-run-1")
    resp = cast("_HttpClient", client).post(
        "/v1/traces",
        json=body,
        # the EXACT header the real OTLP exporter sends — NOT X-API-Key.
        headers={"x-valuemaxx-ingest-key": INGEST_KEY},
    )
    assert resp.status_code == 200, resp.text  # was 404 before the collector existed

    metric = _run_total_cost_metric(client, api_key=INGEST_KEY)
    assert metric.status_code == 200, metric.text
    cells = metric.json()["cells"]
    assert len(cells) == 1
    # the int tokens decoded correctly (string intValue -> native int) and the cost landed.
    assert Decimal(cells[0]["numerator_value"]) == _COST_USD


def test_otlp_collector_rejects_unknown_key(client: TestClient) -> None:
    """An unknown ingest key is 401 — the collector is not an open relay."""
    resp = cast("_HttpClient", client).post(
        "/v1/traces",
        json=_otlp_export_request(run_id="x"),
        headers={"x-valuemaxx-ingest-key": "not-a-real-key"},
    )
    assert resp.status_code == 401, resp.text
