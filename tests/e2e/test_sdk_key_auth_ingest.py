"""Regression e2e: the genuine SDK ingest path is KEY-authenticated, never signed.

This is the real bug guardrail. A real SDK ships spans through a standard OTLP
exporter authenticated with ONLY the per-tenant ingest key (``X-API-Key``); it
cannot HMAC-sign the OTLP body. ``ingest_otlp_span`` was declared
``webhook_inbound`` (signature-required), so a real exporter's spans were 401'd —
the previous e2e masked this by hand-signing the body.

This test exercises the genuine path with NO manual HMAC anywhere:

1. The real :func:`~valuemaxx.server.app.create_app` boots over a fresh temp SQLite
   DB through Starlette's ``TestClient`` (migrations run; the capture runtime wires).
2. The real Python SDK (:func:`valuemaxx.sdk.init`) instruments an injected fake LLM
   client; the sink ships each captured span to ``/ingest_otlp_span`` with ONLY the
   ``X-API-Key`` header (key-auth) — the exact auth a real OTLP exporter sends.
3. The CostEvent lands in the store under the right tenant with the right cost,
   proven by querying it back through ``/run_metric`` — not by inspecting internals.

If ``ingest_otlp_span`` ever regresses to a signed route, the key-only POST 401s and
this test fails — the bug class cannot recur silently.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from typing_extensions import override
from valuemaxx.capture import AttemptObservation
from valuemaxx.capture.otlp import semconv
from valuemaxx.core.ids import RunId, TenantId
from valuemaxx.core.repositories import CostEventRepository
from valuemaxx.core.tokens import TokenVector
from valuemaxx.sdk import init, track
from valuemaxx.server.app import create_app
from valuemaxx.server.settings import ServerSettings

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from datetime import datetime

    import httpx
    from valuemaxx.core.cost import CostEvent

# A webhook secret is still configured (signed webhooks like ingest_webhook_outcome
# need it), but the SDK ingest path below NEVER uses it — that is the whole point.
WEBHOOK_SECRET = b"sdk-key-auth-secret"
INGEST_KEY = "user-ingest-key"

_INPUT_TOKENS = 1_000
_OUTPUT_TOKENS = 250
_COST_USD = Decimal("0.0425")


class _Transport:
    """The fake LLM client's transport — stands in for ``client._client`` (httpx)."""

    def send(self, _request: object) -> str:
        return "ok"


class _FakeLlmClient:
    """A fake provider client shaped like the real ones the SDK instruments (H1)."""

    def __init__(self) -> None:
        self._client = _Transport()

    @property
    def transport(self) -> _Transport:
        """The injected transport the SDK instruments (a public accessor for the test)."""
        return self._client


def _usage_extractor(_response: object) -> AttemptObservation:
    """Pull the per-attempt usage off a (fake) provider response (fixed token vector)."""
    return AttemptObservation(
        provider="anthropic",
        model="claude-opus-4-8",
        tokens=TokenVector(
            input_uncached=_INPUT_TOKENS,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=_OUTPUT_TOKENS,
            reasoning=0,
        ),
        is_streaming=False,
    )


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


class _KeyAuthOtlpSink(CostEventRepository):
    """A cost-event sink that ships each captured span over the REAL OTLP wire, KEY-AUTH ONLY.

    ``upsert`` (called by the SDK's bounded Emitter on drain) encodes the CostEvent
    into the ``gen_ai.*`` / ``ai_margin.*`` semconv attributes and POSTs them to
    ``/ingest_otlp_span`` with ONLY the ``X-API-Key`` header — exactly the auth a real
    OTLP exporter sends. There is NO ``X-Signature`` and NO HMAC anywhere: if the
    route demands a signature, this POST 401s and the test fails loudly.
    """

    def __init__(self, client: TestClient, *, api_key: str) -> None:
        self._client = client
        self._api_key = api_key
        self.shipped = 0

    @override
    def upsert(self, tenant_id: TenantId, event: CostEvent) -> None:
        attributes = _cost_event_to_span_attributes(event)
        body = {"tenant_id": str(tenant_id), "attributes": attributes}
        raw = json.dumps(body).encode("utf-8")
        resp = cast("_HttpClient", self._client).post(
            "/ingest_otlp_span",
            content=raw,
            headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
        )
        if resp.status_code != 200:  # pragma: no cover - a wire failure must fail loudly
            raise AssertionError(
                f"key-authenticated ingest_otlp_span rejected the span: "
                f"{resp.status_code} {resp.text}"
            )
        self.shipped += 1

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        return ()  # write-through to the wire; reads happen via /run_metric.

    @override
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        return ()


def _cost_event_to_span_attributes(event: CostEvent) -> dict[str, object]:
    """Encode a captured CostEvent into the OTLP semconv attribute mapping (H3, semconv only)."""
    tokens = event.tokens
    return {
        semconv.GEN_AI_SYSTEM: event.provider,
        semconv.GEN_AI_REQUEST_MODEL: event.model,
        semconv.GEN_AI_USAGE_INPUT_TOKENS: tokens.total_input,
        semconv.GEN_AI_USAGE_OUTPUT_TOKENS: tokens.output,
        semconv.AI_MARGIN_CACHE_READ: tokens.cache_read,
        semconv.AI_MARGIN_CACHE_WRITE_5M: tokens.cache_write_5m,
        semconv.AI_MARGIN_CACHE_WRITE_1H: tokens.cache_write_1h,
        semconv.AI_MARGIN_REASONING: tokens.reasoning,
        semconv.AI_MARGIN_RUN_ID: str(event.run_id),
        semconv.AI_MARGIN_ATTEMPT_ID: str(event.attempt_id),
        semconv.AI_MARGIN_CAPTURE_GRANULARITY: event.capture_granularity.value,
        semconv.AI_MARGIN_COST_USD: str(_COST_USD),
        semconv.AI_MARGIN_IS_STREAMING: event.is_streaming,
        semconv.AI_MARGIN_PARTIAL_RECOVERED: event.partial_recovered,
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
    """The UUID-string tenant bound to the single ingest key."""
    return str(uuid4())


@pytest.fixture
def settings(tmp_path: object, tenant: str) -> ServerSettings:
    """Server settings over a fresh temp SQLite DB with one key->tenant mapping."""
    db_path = Path(str(tmp_path)) / "sdk-key-auth.db"
    return ServerSettings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        ingest_keys={INGEST_KEY: tenant},
        webhook_secret=WEBHOOK_SECRET.decode("utf-8"),
    )


@pytest.fixture
def client(settings: ServerSettings) -> Iterator[TestClient]:
    """The booted backend: real create_app, real lifespan, real temp-SQLite store."""
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def test_genuine_sdk_key_auth_ingest_lands_in_store(client: TestClient, tenant: str) -> None:
    """The genuine SDK exporter auth path (key only, no signing) persists a queryable CostEvent."""
    tenant_id = TenantId(UUID(tenant))

    # The REAL SDK instruments an injected fake LLM client; the sink ships captured cost
    # over the REAL OTLP wire with ONLY the ingest key (no signature anywhere).
    sink = _KeyAuthOtlpSink(client, api_key=INGEST_KEY)
    fake_client = _FakeLlmClient()
    result = init(
        tenant_id=tenant_id,
        ingest_key="byo-key-never-logged",
        endpoint="https://ingest.example",
        client=fake_client,
        sink=sink,
        usage_extractor=_usage_extractor,
    )
    assert result.capture_patched is True, result.warnings
    handle = result.instrument_handle
    assert handle is not None

    with track.run(run_id="key-auth-run"):
        fake_client.transport.send(object())
    handle.handle_drain()  # off-path drain -> the sink ships the span over the key-auth wire
    handle.uninstrument()

    # The span reached the store over key-auth alone (no 401, no signature).
    assert sink.shipped == 1, "the captured span must reach the store via key-auth"

    # The CostEvent landed under the right tenant with the right cost — proven by querying
    # it back through the real query capability, never by inspecting internals.
    metric = _run_total_cost_metric(client, api_key=INGEST_KEY)
    assert metric.status_code == 200, metric.text
    cells = metric.json()["cells"]
    assert len(cells) == 1
    assert Decimal(cells[0]["numerator_value"]) == _COST_USD
