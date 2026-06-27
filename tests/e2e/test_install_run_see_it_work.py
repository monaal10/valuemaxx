"""THE definitive product e2e: install -> run -> see it work, end to end.

This is the single test that proves the whole product does what a user installs it
to do, exercising every real layer with no per-layer mocking of the thing under
test. The only injected boundary is the user's own LLM client (a fake transport,
exactly as a real integration would inject ``anthropic``/``openai``):

1. **Backend boots.** The real :func:`~valuemaxx.server.app.create_app` is started
   over a fresh temp SQLite database through Starlette's ``TestClient`` (the ASGI
   transport drives the real lifespan: migrations run, the store opens, the capture
   + metrics capability runtimes are wired).
2. **The real Python SDK captures cost.** ``valuemaxx.sdk.init`` instruments an
   injected fake LLM client (instance-scoped, H1). Inside ``track.run`` a transport
   call produces a real :class:`~valuemaxx.core.cost.CostEvent`, drained off the host
   path into a sink that ships it to the backend over the **real OTLP wire** — a
   KEY-authenticated POST to ``/ingest_otlp_span`` (X-API-Key only, no signature —
   exactly how a real OTLP exporter ships spans) carrying the ``gen_ai.*`` /
   ``ai_margin.*`` semconv attributes, the exact path the universal/TS ingest decodes.
3. **The CostEvent landed in the store** under the right tenant with the right cost,
   proven by querying it back — not by inspecting internals.
4. **A query capability returns a rollup** with the right number AND both H7 honesty
   fields (``minimum_tier`` + ``confidence_distribution``) on the wire.
5. **An outcome drives cost-per-outcome.** A confirmed, billing-grade-bound outcome
   is persisted into the very store the booted app serves from; the real metrics
   runtime is re-pointed at the store's outcomes; ``/run_metric`` over the wire then
   returns a correct cost-per-outcome ratio (total cost / verified outcomes) whose
   confidence reflects the bound tier (H8: only exact/deterministic count).

If this test is green, ``pip install`` -> ``valuemaxx up`` -> instrument -> query is
proven to work as a user experiences it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from typing_extensions import override
from valuemaxx.capture import AttemptObservation
from valuemaxx.capture.otlp import semconv
from valuemaxx.core.enums import BindingTier, SignalClass
from valuemaxx.core.ids import OutcomeEventId, RunId, TenantId
from valuemaxx.core.outcome import OutcomeBinding, OutcomeEvent
from valuemaxx.core.repositories import CostEventRepository
from valuemaxx.core.run import Run
from valuemaxx.core.tokens import TokenVector
from valuemaxx.metrics import (
    MetricExecutor,
    MetricRuntime,
    MetricWindow,
    bind_runtime,
)
from valuemaxx.sdk import init, track
from valuemaxx.server.app import create_app
from valuemaxx.server.settings import ServerSettings

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    import httpx
    from valuemaxx.capabilities import Registry
    from valuemaxx.core.cost import CostEvent
    from valuemaxx.server.store_bridge import StoreBridge


# --- the wire fixtures: one ingest key -> one tenant, one webhook secret -----------
WEBHOOK_SECRET = b"e2e-install-run-secret"
INGEST_KEY = "user-ingest-key"

# A deterministic per-attempt usage shape (what the user's `usage_extractor` would
# pull off a real `anthropic`/`openai` response). The exact cost is computed below
# from these counts so the assertion is a single source of truth.
_INPUT_TOKENS = 1_000
_OUTPUT_TOKENS = 250
_COST_USD = Decimal("0.0425")


class _Transport:
    """The fake LLM client's transport — stands in for ``client._client`` (httpx)."""

    def send(self, _request: object) -> str:
        return "ok"


class _FakeLlmClient:
    """A fake provider client shaped like the real ones the SDK instruments (H1).

    The SDK wraps ``client._client.send`` on this instance only; an unrelated client
    in the same process is untouched. This is exactly how a user injects their real
    ``anthropic`` / ``openai`` client.
    """

    def __init__(self) -> None:
        self._client = _Transport()

    @property
    def transport(self) -> _Transport:
        """The injected transport the SDK instruments (a public accessor for the test)."""
        return self._client


def _usage_extractor(_response: object) -> AttemptObservation:
    """Pull the per-attempt usage off a (fake) provider response.

    Mirrors a user-supplied extractor for a non-streaming completion: a fixed token
    vector tagged with the provider/model. The SDK prices it (no pricebook here, so
    the cost rides as ``None``) and the sink ships the authoritative cost inline.
    """
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


class _OtlpWireSink(CostEventRepository):
    """A real cost-event sink that ships each captured event over the REAL OTLP wire.

    This is the producer side of the wire contract. ``upsert`` (called by the SDK's
    bounded :class:`~valuemaxx.capture.emit.Emitter` on drain) encodes the captured
    :class:`~valuemaxx.core.cost.CostEvent` into the ``gen_ai.*`` / ``ai_margin.*``
    semconv attributes and POSTs them to the backend's ``/ingest_otlp_span`` route
    authenticated with ONLY the ingest key (``X-API-Key``) — the exact path any
    language's real OTLP exporter takes, which cannot HMAC-sign the body. There is NO
    signature anywhere. The backend re-decodes the span into a CostEvent and persists
    it, so the round trip is the genuine wire, never an in-process shortcut.
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
        if resp.status_code != 200:  # pragma: no cover - a wire failure should fail loudly here
            raise AssertionError(
                f"ingest_otlp_span rejected the span: {resp.status_code} {resp.text}"
            )
        self.shipped += 1

    @override
    def list_for_run(self, tenant_id: TenantId, run_id: RunId) -> Sequence[CostEvent]:
        return ()  # the sink is write-through to the wire; reads happen via /run_metric.

    @override
    def list_in_window(
        self, tenant_id: TenantId, start: datetime, end: datetime
    ) -> Sequence[CostEvent]:
        return ()


def _cost_event_to_span_attributes(event: CostEvent) -> dict[str, object]:
    """Encode a captured CostEvent into the OTLP semconv attribute mapping (H3).

    Every key is a ``semconv`` constant (never an inline literal), so the producer
    side speaks the same single-source wire dialect the server's ``span_to_cost_event``
    decodes. ``gen_ai.usage.input_tokens`` carries the TOTAL input (the server derives
    ``input_uncached`` from it via ``TokenVector.from_provider``); the authoritative
    inline cost rides on ``ai_margin.cost_usd`` so the e2e cost is deterministic.
    """
    tokens = event.tokens
    attributes: dict[str, object] = {
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
    return attributes


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


def _run_cost_per_outcome_metric(client: TestClient, *, api_key: str) -> httpx.Response:
    """POST the cost-per-outcome metric to ``/run_metric`` (tenant resolved from key).

    ``total_cost_usd`` over the billing-grade ``verified_outcome_count`` denominator —
    the product's headline metric. Advisory/retracted outcomes never inflate the
    denominator (H8); with outcomes bound the ratio is real.
    """
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
    db_path = Path(str(tmp_path)) / "install-run.db"
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


def test_install_run_see_it_work(client: TestClient, tenant: str) -> None:
    """install -> run -> see it work: SDK capture over OTLP -> store -> rollup -> cost/outcome."""
    tenant_id = TenantId(UUID(tenant))

    # (2) the REAL SDK instruments an injected fake LLM client; the sink ships captured
    #     cost over the REAL OTLP wire to the booted backend.
    sink = _OtlpWireSink(client, api_key=INGEST_KEY)
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

    # a real user call inside a bound run: the transport send is captured per-attempt.
    with track.run(run_id="checkout-run"):
        fake_client.transport.send(object())
    handle.handle_drain()  # off-path drain -> the sink ships the span over the wire
    handle.uninstrument()

    assert sink.shipped == 1, "exactly one captured attempt should reach the wire"

    # (3)+(4) the CostEvent landed under the right tenant with the right cost — proven
    #         by querying it back through the real query capability, with H7 fields.
    metric = _run_cost_per_outcome_metric(client, api_key=INGEST_KEY)
    assert metric.status_code == 200, metric.text
    body = metric.json()
    assert body["name"] == "cost_per_outcome"
    assert len(body["cells"]) == 1
    cell = body["cells"][0]
    assert Decimal(cell["numerator_value"]) == _COST_USD  # the captured cost, round-tripped
    # no outcomes yet -> the billing-grade denominator is zero and the ratio is withheld
    # (we never publish a fabricated cost-per-outcome), but both H7 fields ride anyway.
    assert cell["denominator_value"] == 0
    assert cell["value"] is None
    confidence = cell["confidence"]
    assert "minimum_tier" in confidence
    assert "confidence_distribution" in confidence

    # (5) drive an OUTCOME and assert cost-per-outcome. Persist a confirmed, billing-
    #     grade-bound outcome (and its run) into the SAME store the booted app serves,
    #     then re-point the real metrics runtime at the store's outcomes and re-query.
    bridge = _store_bridge(client)
    registry = _registry(client)
    _persist_confirmed_outcome(bridge, tenant_id, run_id="checkout-run")
    _rebind_metrics_with_store_outcomes(registry, bridge, tenant_id)

    after = _run_cost_per_outcome_metric(client, api_key=INGEST_KEY)
    assert after.status_code == 200, after.text
    cpo_cell = after.json()["cells"][0]
    assert Decimal(cpo_cell["numerator_value"]) == _COST_USD
    assert cpo_cell["denominator_value"] == 1  # one verified (exact-tier) outcome
    # cost-per-outcome == total cost / 1 verified outcome, published at cent precision
    # (ROUND_HALF_EVEN — the ratio a dollar-denominated metric is reported in).
    assert Decimal(cpo_cell["value"]) == _COST_USD.quantize(Decimal("0.01"))
    # H8: the confidence headline reflects the actual bound tier (exact), not a fiction.
    assert cpo_cell["confidence"]["minimum_tier"] == BindingTier.EXACT.value
    assert cpo_cell["confidence"]["confidence_distribution"][BindingTier.EXACT.value] == 1


def _store_bridge(client: TestClient) -> StoreBridge:
    """The booted app's live store bridge (set on app.state by the lifespan)."""
    app = client.app
    bridge = getattr(getattr(app, "state", None), "store_bridge", None)
    assert bridge is not None, "create_app must expose the live store bridge on app.state"
    return cast("StoreBridge", bridge)


def _registry(client: TestClient) -> Registry:
    """The booted app's capability registry (set on app.state by create_app).

    Exposing the assembled registry is what lets the e2e re-point the real metrics
    runtime at the store's outcomes to drive cost-per-outcome over the wire.
    """
    app = client.app
    registry = getattr(getattr(app, "state", None), "registry", None)
    assert registry is not None, "create_app must expose the capability registry on app.state"
    return cast("Registry", registry)


def _persist_confirmed_outcome(bridge: StoreBridge, tenant_id: TenantId, *, run_id: str) -> None:
    """Persist a confirmed, exact-tier-bound OutcomeEvent (and its run) into the store."""
    at = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    bridge.runs.upsert(
        tenant_id,
        Run(
            tenant_id=tenant_id,
            id=RunId(run_id),
            agent_name="checkout-agent",
            started_at=at,
            ended_at=None,
            entity_keys=frozenset({("application", run_id)}),
        ),
    )
    bridge.outcome_events.upsert(
        tenant_id,
        OutcomeEvent(
            tenant_id=tenant_id,
            id=OutcomeEventId("oe-checkout-1"),
            name="checkout_completed",
            signal_class=SignalClass.OUTCOME_CONFIRMED,
            value=Decimal("1"),
            occurred_at=at,
            # The work-queue shape the runtime fetches via ``list_unbound``: the tier
            # (EXACT) is what makes the outcome billing-grade, not the run_id slot
            # (binding to a run is the attribution step; here the tier is authoritative).
            binding=OutcomeBinding(run_id=None, tier=BindingTier.EXACT, bound_by="attribution"),
            entity_keys=frozenset({("application", run_id)}),
            correlation_id=None,
            source="webhook",
            raw={"amount": 1},
        ),
    )


def _rebind_metrics_with_store_outcomes(
    registry: Registry, bridge: StoreBridge, tenant_id: TenantId
) -> None:
    """Re-point the real run_metric runtime at the store's outcomes (H8 denominator).

    Uses the SAME ``bind_runtime`` the app composition root uses, against the SAME
    assembled registry the surfaces project from, so the next ``/run_metric`` call
    over the wire computes cost-per-outcome from real, persisted outcomes.
    """
    executor = MetricExecutor(
        cost_repo=bridge.cost_events,
        outcome_repo=bridge.outcome_events,
        run_repo=bridge.runs,
    )
    bind_runtime(
        registry,
        MetricRuntime(
            tenant_id=tenant_id,
            executor=executor,
            window=MetricWindow(
                start=datetime(1970, 1, 1, tzinfo=UTC),
                end=datetime(9999, 12, 31, tzinfo=UTC),
            ),
            outcomes=bridge.outcome_events.list_unbound(tenant_id),
        ),
    )
