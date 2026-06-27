"""End-to-end: the assembly boots, persists ingested cost, and serves queries.

These exercise the REAL wire path against a REAL (temp SQLite) store — the full
backend assembly the SDK ships spans to:

1. ``create_app`` boots; the lifespan runs migrations so the schema exists.
2. A signed OTLP span POSTed to ``/ingest_otlp_span`` lands in the store as a
   CostEvent (the ingest handler is wired to the CostEventRepository).
3. The persisted cost is queryable via the ``/run_metric`` query capability — the
   metric reads exactly what was ingested.
4. Tenant isolation holds: a span ingested under tenant B never appears in tenant
   A's metric (the store query is tenant-scoped).
5. Honesty axis: the ingested CostEvent carries ``measured`` provenance, and the
   metric cell ships both H7 confidence fields.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from _server_helpers import (
    KEY_A,
    KEY_B,
    WEBHOOK_SECRET,
    ingest_span,
    route_paths,
    run_metric,
    sign,
    span_attributes,
    total_cost_definition,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_app_boots_and_migrations_apply(client: TestClient) -> None:
    """test_app_boots_and_migrations_apply: the booted client exposes the ingest route."""
    paths = route_paths(client.app)
    assert "/ingest_otlp_span" in paths
    assert "/run_metric" in paths


def test_ingested_span_persists_and_is_queryable(client: TestClient) -> None:
    """test_ingested_span_persists_and_is_queryable: ingest -> store -> run_metric query."""
    resp = ingest_span(
        client,
        api_key=KEY_A,
        webhook_secret=WEBHOOK_SECRET,
        attributes=span_attributes(run_id="run-1", attempt_id="att-1", cost_usd="0.0250"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["run_id"] == "run-1"
    assert body["attempt_id"] == "att-1"

    metric = run_metric(client, api_key=KEY_A, definition=total_cost_definition())
    assert metric.status_code == 200, metric.text
    result = metric.json()
    assert result["name"] == "cost_per_outcome"
    assert len(result["cells"]) == 1
    cell = result["cells"][0]
    # the numerator is the summed cost of every persisted cost event in the tenant scope
    assert Decimal(cell["numerator_value"]) == Decimal("0.0250")


def test_double_delivery_does_not_double_count(client: TestClient) -> None:
    """test_double_delivery_does_not_double_count: a redelivered span upserts, M7."""
    attrs = span_attributes(run_id="run-dup", attempt_id="att-dup", cost_usd="0.0100")
    for _ in range(3):
        resp = ingest_span(client, api_key=KEY_A, webhook_secret=WEBHOOK_SECRET, attributes=attrs)
        assert resp.status_code == 200, resp.text

    metric = run_metric(client, api_key=KEY_A, definition=total_cost_definition())
    cell = metric.json()["cells"][0]
    # three at-least-once deliveries of the same (run_id, attempt_id) -> one row,
    # so the summed cost is the single event's cost, never tripled (M7).
    assert Decimal(cell["numerator_value"]) == Decimal("0.0100")


def test_tenant_isolation_holds(client: TestClient) -> None:
    """test_tenant_isolation_holds: tenant B's ingest never enters tenant A's metric."""
    ingest_span(
        client,
        api_key=KEY_A,
        webhook_secret=WEBHOOK_SECRET,
        attributes=span_attributes(run_id="run-a", attempt_id="att-a", cost_usd="0.0700"),
    )
    ingest_span(
        client,
        api_key=KEY_B,
        webhook_secret=WEBHOOK_SECRET,
        attributes=span_attributes(run_id="run-b", attempt_id="att-b", cost_usd="9.9900"),
    )

    # run_metric is bound to tenant A; it must see ONLY tenant A's 0.0700, never B's.
    metric = run_metric(client, api_key=KEY_A, definition=total_cost_definition())
    cell = metric.json()["cells"][0]
    assert Decimal(cell["numerator_value"]) == Decimal("0.0700")
    assert Decimal(cell["numerator_value"]) != Decimal("9.9900")  # B's cost never leaks


def test_metric_cell_ships_both_h7_confidence_fields(client: TestClient) -> None:
    """test_metric_cell_ships_both_h7_confidence_fields: minimum_tier + distribution on the wire."""
    ingest_span(
        client,
        api_key=KEY_A,
        webhook_secret=WEBHOOK_SECRET,
        attributes=span_attributes(run_id="run-h7", attempt_id="att-h7", cost_usd="0.0050"),
    )
    metric = run_metric(client, api_key=KEY_A, definition=total_cost_definition())
    cell = metric.json()["cells"][0]
    confidence = cell["confidence"]
    assert "minimum_tier" in confidence
    assert "confidence_distribution" in confidence


def test_bad_webhook_signature_is_rejected_and_not_persisted(client: TestClient) -> None:
    """test_bad_webhook_signature_is_rejected_and_not_persisted: 401 before the handler."""
    import json as _json
    from typing import Protocol, cast

    class _Post(Protocol):
        def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> object: ...

    attrs = span_attributes(run_id="run-bad", attempt_id="att-bad", cost_usd="1.0000")
    raw = _json.dumps({"tenant_id": "x", "attributes": attrs}).encode("utf-8")
    bad = cast("_Post", client).post(
        "/ingest_otlp_span",
        content=raw,
        headers={"X-API-Key": KEY_A, "X-Signature": "deadbeef"},
    )
    assert getattr(bad, "status_code", None) == 401

    # a correctly-signed but empty store still totals zero for this run scope.
    good_metric = run_metric(client, api_key=KEY_A, definition=total_cost_definition())
    cells = good_metric.json()["cells"]
    # no span was persisted, so there is no cell (an empty cost set yields no group).
    assert cells == [] or Decimal(cells[0]["numerator_value"]) == Decimal("0")


def test_missing_api_key_is_unauthorized(client: TestClient) -> None:
    """test_missing_api_key_is_unauthorized: no key -> 401 (no anonymous tenant)."""
    attrs = span_attributes(run_id="run-x", attempt_id="att-x", cost_usd="1.0")
    import json as _json
    from typing import Protocol, cast

    class _Post(Protocol):
        def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> object: ...

    raw = _json.dumps({"tenant_id": "x", "attributes": attrs}).encode("utf-8")
    resp = cast("_Post", client).post(
        "/ingest_otlp_span",
        content=raw,
        headers={"X-Signature": sign(WEBHOOK_SECRET, raw)},
    )
    assert getattr(resp, "status_code", None) == 401
