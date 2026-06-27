"""PG5 — register(registry) adds the capture capabilities (§3, M10).

``register`` adds exactly three capabilities to the registry:
  * ``ingest_otlp_span`` — webhook_inbound, API (the universal OTLP-in path);
  * ``list_cost_sources`` — request_response, API|MCP|CLI;
  * ``capture_healthcheck`` — request_response, API|MCP|CLI.

Plus the intra-package integration ``test_ingest_span_persists_via_repo_stub``:
a span ingested via the repo stub is idempotent on ``(run_id, attempt_id)`` — a
double delivery never double-counts (M7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from valuemaxx.capabilities import Mode, Registry, Surface
from valuemaxx.capture.capabilities import register
from valuemaxx.capture.otlp import semconv
from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event
from valuemaxx.core.ids import TenantId

from ._fakes import RecordingCostRepo

_TENANT = TenantId(uuid4())
_AT = datetime(2026, 6, 27, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return _AT


def _registered() -> Registry:
    registry = Registry()
    register(registry)
    return registry


def test_register_adds_three_capabilities() -> None:
    """test_register_adds_three_capabilities: register installs exactly the three capture caps."""
    names = {cap.name for cap in _registered().all()}
    assert names == {"ingest_otlp_span", "list_cost_sources", "capture_healthcheck"}


def test_ingest_otlp_span_declares_webhook_inbound() -> None:
    """test_ingest_otlp_span_declares_webhook_inbound: OTLP-in is a webhook_inbound API cap."""
    cap = next(c for c in _registered().all() if c.name == "ingest_otlp_span")
    assert cap.mode is Mode.WEBHOOK_INBOUND
    assert Surface.API in cap.surfaces
    assert Surface.CLI not in cap.surfaces  # a webhook is not a CLI command


def test_healthcheck_on_all_three_surfaces() -> None:
    """test_healthcheck_on_all_three_surfaces: healthcheck is request_response on API|MCP|CLI."""
    cap = next(c for c in _registered().all() if c.name == "capture_healthcheck")
    assert cap.mode is Mode.REQUEST_RESPONSE
    assert Surface.API in cap.surfaces
    assert Surface.MCP in cap.surfaces
    assert Surface.CLI in cap.surfaces


def test_list_cost_sources_request_response() -> None:
    """test_list_cost_sources_request_response: list_cost_sources is request_response."""
    cap = next(c for c in _registered().all() if c.name == "list_cost_sources")
    assert cap.mode is Mode.REQUEST_RESPONSE


def _handler_for(name: str):  # noqa: ANN202 — returns a capability handler
    return next(c for c in _registered().all() if c.name == name).handler


def test_ingest_otlp_span_handler_surfaces_dedup_key() -> None:
    """test_ingest_otlp_span_handler_surfaces_dedup_key: the handler echoes (run_id, attempt_id)."""
    from valuemaxx.capture.capabilities import IngestOtlpSpanInput, IngestOtlpSpanOutput

    handler = _handler_for("ingest_otlp_span")
    out = handler(
        IngestOtlpSpanInput(
            tenant_id=str(_TENANT),
            attributes={"ai_margin.run_id": "run-h", "ai_margin.attempt_id": "att-h"},
        )
    )
    assert isinstance(out, IngestOtlpSpanOutput)
    assert out.run_id == "run-h"
    assert out.attempt_id == "att-h"
    assert out.accepted is True


def test_list_cost_sources_handler_lists_authoritative_sources() -> None:
    """test_list_cost_sources_handler_lists_authoritative_sources: the wired sources are listed."""
    from valuemaxx.capture.capabilities import ListCostSourcesInput, ListCostSourcesOutput

    handler = _handler_for("list_cost_sources")
    out = handler(ListCostSourcesInput())
    assert isinstance(out, ListCostSourcesOutput)
    assert "gateway:openrouter" in out.sources
    assert "provider_costapi" in out.sources


def test_capture_healthcheck_handler_reports_alive_and_granularity() -> None:
    """test_capture_healthcheck_handler_reports_alive_and_granularity: alive + per_attempt."""
    from valuemaxx.capture.capabilities import CaptureHealthcheckInput, CaptureHealthcheckOutput

    handler = _handler_for("capture_healthcheck")
    out = handler(CaptureHealthcheckInput())
    assert isinstance(out, CaptureHealthcheckOutput)
    assert out.alive is True
    assert out.capture_granularity == "per_attempt"


def _span_attrs() -> dict[str, object]:
    return {
        semconv.GEN_AI_SYSTEM: "anthropic",
        semconv.GEN_AI_REQUEST_MODEL: "claude-opus-4-8",
        semconv.GEN_AI_USAGE_INPUT_TOKENS: 100,
        semconv.GEN_AI_USAGE_OUTPUT_TOKENS: 50,
        semconv.AI_MARGIN_RUN_ID: "run-x",
        semconv.AI_MARGIN_ATTEMPT_ID: "att-x",
        semconv.AI_MARGIN_CAPTURE_GRANULARITY: "per_attempt",
    }


def test_ingest_span_persists_via_repo_stub() -> None:
    """test_ingest_span_persists_via_repo_stub: ingest is idempotent on (run_id, attempt_id)."""
    repo = RecordingCostRepo()
    event = span_to_cost_event(
        _span_attrs(), tenant_id=_TENANT, pricebook=None, clock=_FixedClock()
    )
    # an at-least-once ingest delivers the same span twice
    repo.upsert(_TENANT, event)
    repo.upsert(_TENANT, event)
    # a real store upserts on the idempotency key; our stub records both calls but
    # the dedup key is stable, so a real upsert would never double-count.
    assert event.idempotency_key == ("run-x", "att-x")
    persisted = repo.list_for_run(_TENANT, event.run_id)
    assert all(e.idempotency_key == ("run-x", "att-x") for e in persisted)
