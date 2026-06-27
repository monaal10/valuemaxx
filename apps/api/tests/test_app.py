"""API app tests — every API capability becomes a route; tenant isolation holds.

The FastAPI app is a thin projection of the registry: each ``Surface.API``
capability is projected onto a route by mode (request_response -> POST; async_job ->
submit + GET /jobs/{id}; webhook_inbound -> signed receiver). Nothing without the
API surface gets a route. Auth resolves the tenant from the API key; a request
authenticated as tenant A can never read tenant B. Rollup responses carry both H7
fields.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from _api_helpers import (
    get,
    post,
    registry_with_notes,
    registry_with_tuple_capability,
    route_paths,
)
from fastapi.testclient import TestClient
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.api.app import build_app
from valuemaxx.capabilities import Mode, Surface

if TYPE_CHECKING:
    from valuemaxx.capabilities import Registry

_API_KEYS = {"key-a": "tenant-a", "key-b": "tenant-b"}
_WEBHOOK_SECRET = b"shhh-webhook-secret"

# A UUID-valued tenant for capabilities whose handler validates tenant_id as a UUID
# (e.g. the allocation rollup). The API key map binds a key to this tenant.
_UUID_TENANT = str(uuid4())
_UUID_API_KEYS = {**_API_KEYS, "key-uuid": _UUID_TENANT}


def _client(
    registry: Registry | None = None, *, api_keys: dict[str, str] | None = None
) -> TestClient:
    app = build_app(
        registry if registry is not None else build_default_registry(),
        api_keys=api_keys if api_keys is not None else _API_KEYS,
        webhook_secret=_WEBHOOK_SECRET,
    )
    return TestClient(app)


# --- every API capability becomes a route, and nothing else -------------------


def test_every_request_response_api_capability_has_a_post_route() -> None:
    """Each request_response API capability is reachable at POST /{name}."""
    registry = build_default_registry()
    client = _client(registry)
    paths = route_paths(client.app)
    for cap in registry.for_surface(Surface.API):
        if cap.mode is Mode.REQUEST_RESPONSE:
            assert f"/{cap.name}" in paths


def test_async_job_capability_has_submit_and_poll_routes() -> None:
    """Each async_job API capability has a submit POST and a job-poll GET."""
    registry = build_default_registry()
    client = _client(registry)
    paths = route_paths(client.app)
    has_async = any(cap.mode is Mode.ASYNC_JOB for cap in registry.for_surface(Surface.API))
    assert has_async, "expected at least one async_job API capability in the registry"
    for cap in registry.for_surface(Surface.API):
        if cap.mode is Mode.ASYNC_JOB:
            assert f"/{cap.name}" in paths
    assert "/jobs/{job_id}" in paths


def test_non_api_capability_has_no_route() -> None:
    """A capability that does not declare API is never projected onto a route."""
    registry = build_default_registry()
    client = _client(registry)
    paths = route_paths(client.app)
    non_api = [c for c in registry.all() if Surface.API not in c.surfaces]
    for cap in non_api:
        assert f"/{cap.name}" not in paths


# --- tenant isolation ---------------------------------------------------------


def test_missing_api_key_is_401() -> None:
    """A request with no API key is rejected (no unauthenticated capability route)."""
    client = _client(registry_with_notes())
    resp = post(client, "/list_notes", json={})
    assert resp.status_code == 401


def test_bad_api_key_is_401() -> None:
    """A request with an unknown API key is rejected."""
    client = _client(registry_with_notes())
    resp = post(client, "/list_notes", json={}, headers={"X-API-Key": "nope"})
    assert resp.status_code == 401


def test_tenant_a_reads_only_tenant_a() -> None:
    """Tenant A's key only ever sees tenant A's rows (the handler gets A's id)."""
    client = _client(registry_with_notes())
    resp = post(client, "/list_notes", json={}, headers={"X-API-Key": "key-a"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == "tenant-a"
    assert body["notes"] == ["a-secret-note"]
    assert "b-secret-note" not in body["notes"]


def test_tenant_a_cannot_read_tenant_b() -> None:
    """A body claiming tenant B while authenticated as A is forced back to A (no leak)."""
    client = _client(registry_with_notes())
    resp = post(
        client,
        "/list_notes",
        json={"tenant_id": "tenant-b"},  # attempt to read B's data
        headers={"X-API-Key": "key-a"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # the authenticated tenant overrides the body — A never sees B's notes
    assert body["tenant_id"] == "tenant-a"
    assert "b-secret-note" not in body["notes"]


# --- wire validation uses JSON-mode coercion (a JSON array -> a tuple field) ---


def test_tuple_field_accepts_a_json_array_on_the_wire() -> None:
    """A JSON array validates into a strict ``tuple[str, ...]`` capability field.

    The body is parsed JSON; strict pydantic rejects a Python ``list`` for a tuple
    in dict mode but accepts a JSON array in JSON mode. The projection must validate
    with JSON-mode semantics so the wire contract matches what JSON can express.
    """
    client = _client(registry_with_tuple_capability())
    resp = post(client, "/echo_tags", json={"tags": ["a", "b"]}, headers={"X-API-Key": "key-a"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tags"] == ["a", "b"]


# --- rollup responses carry both H7 fields ------------------------------------


def test_rollup_response_carries_h7_fields() -> None:
    """A rollup-returning route's response carries minimum_tier + confidence_distribution."""
    client = _client(api_keys=_UUID_API_KEYS)
    resp = post(
        client,
        "/allocated_cost_rollup",
        json={
            "run_id": "run-1",
            "measured_costs": ["10.00"],
            "shared_costs_yaml": "",
            "weights": {},
            "total_true_cost_estimate": "10.00",
        },
        headers={"X-API-Key": "key-uuid"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "minimum_tier" in body
    assert "confidence_distribution" in body


# --- async_job submit + poll --------------------------------------------------


def test_async_job_submit_returns_job_id_then_polls() -> None:
    """Submitting an async_job returns a job_id promptly; polling returns its status."""
    client = _client()
    # run_eval_funnel is an async_job capability; submit with a minimal valid body.
    submit = post(
        client,
        "/run_eval_funnel",
        json={
            "tenant_id": "tenant-a",
            "candidate_model": "claude-haiku",
            "incumbent_model": "claude-sonnet",
            "candidate_provider": "anthropic",
            "candidate_secret_ref": "secret-ref",
            "label_source": "human_labeled",
        },
        headers={"X-API-Key": "key-a"},
    )
    assert submit.status_code == 202, submit.text
    job_id = submit.json()["job_id"]
    assert job_id
    poll = get(client, f"/jobs/{job_id}", headers={"X-API-Key": "key-a"})
    assert poll.status_code == 200, poll.text
    assert poll.json()["job_id"] == job_id
    assert poll.json()["status"] in {"succeeded", "failed", "running"}


def test_poll_unknown_job_is_404() -> None:
    """Polling a job id that does not exist is a 404."""
    client = _client()
    resp = get(client, "/jobs/does-not-exist", headers={"X-API-Key": "key-a"})
    assert resp.status_code == 404


def test_async_job_success_returns_result() -> None:
    """A succeeding async_job is polled to a succeeded status carrying its result."""
    import time

    from _api_helpers import ListNotesInput, ListNotesOutput
    from valuemaxx.capabilities import Registry, capability

    def _ok(request: ListNotesInput) -> ListNotesOutput:
        return ListNotesOutput(tenant_id=request.tenant_id, notes=("done",))

    registry = Registry()
    registry.register(
        capability(
            name="slow_notes",
            input_model=ListNotesInput,
            output_model=ListNotesOutput,
            handler=_ok,
            description="A long-running notes job (succeeds).",
            surfaces=Surface.API,
            mode=Mode.ASYNC_JOB,
        )
    )
    client = _client(registry)
    submit = post(client, "/slow_notes", json={}, headers={"X-API-Key": "key-a"})
    assert submit.status_code == 202, submit.text
    job_id = submit.json()["job_id"]
    body: dict[str, object] = {"status": "running"}
    for _ in range(50):
        body = get(client, f"/jobs/{job_id}", headers={"X-API-Key": "key-a"}).json()
        if body["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert body["status"] == "succeeded"
    result = body["result"]
    assert isinstance(result, dict)
    assert result["tenant_id"] == "tenant-a"
    assert result["notes"] == ["done"]


def test_async_job_reaches_terminal_status() -> None:
    """An unbound eval funnel job reaches a terminal status (failed: not wired)."""
    import time

    client = _client()
    submit = post(
        client,
        "/run_eval_funnel",
        json={
            "tenant_id": "tenant-a",
            "candidate_model": "claude-haiku",
            "incumbent_model": "claude-sonnet",
            "candidate_provider": "anthropic",
            "candidate_secret_ref": "secret-ref",
            "label_source": "human_labeled",
        },
        headers={"X-API-Key": "key-a"},
    )
    job_id = submit.json()["job_id"]
    body: dict[str, object] = {"status": "running", "error": None}
    for _ in range(50):
        body = get(client, f"/jobs/{job_id}", headers={"X-API-Key": "key-a"}).json()
        if body["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    # the eval runtime is not bound in this app, so the job fails (never crashes the API)
    assert body["status"] == "failed"
    assert body["error"] is not None


def test_poll_job_is_tenant_scoped() -> None:
    """Tenant B cannot poll tenant A's job (cross-tenant poll is a 404)."""
    client = _client()
    submit = post(
        client,
        "/run_eval_funnel",
        json={
            "tenant_id": "tenant-a",
            "candidate_model": "claude-haiku",
            "incumbent_model": "claude-sonnet",
            "candidate_provider": "anthropic",
            "candidate_secret_ref": "secret-ref",
            "label_source": "human_labeled",
        },
        headers={"X-API-Key": "key-a"},
    )
    job_id = submit.json()["job_id"]
    cross = get(client, f"/jobs/{job_id}", headers={"X-API-Key": "key-b"})
    assert cross.status_code == 404


# --- webhook signature verification ------------------------------------------


def test_webhook_rejects_bad_signature() -> None:
    """A webhook with a wrong signature is 401 and the handler is never called."""
    client = _client()
    raw = json.dumps({"source": "stripe", "event": "charge"}).encode()
    resp = post(
        client,
        "/ingest_otlp_span",
        content=raw,
        headers={"X-API-Key": "key-a", "X-Signature": "deadbeef"},
    )
    assert resp.status_code == 401


def test_webhook_accepts_valid_signature() -> None:
    """A webhook with a valid HMAC over the raw body is accepted."""
    client = _client()
    raw = json.dumps({"tenant_id": "tenant-a", "attributes": {"ai_margin.run_id": "r1"}}).encode()
    signature = hmac.new(_WEBHOOK_SECRET, raw, hashlib.sha256).hexdigest()
    resp = post(
        client,
        "/ingest_otlp_span",
        content=raw,
        headers={"X-API-Key": "key-a", "X-Signature": signature},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("path", ["/list_notes"])
def test_request_validation_uses_capability_input_model(path: str) -> None:
    """A request is validated against the capability input model; tenant is overridden."""
    client = _client(registry_with_notes())
    resp = post(
        client,
        path,
        json={"tenant_id": "tenant-b"},  # the authenticated tenant overrides this
        headers={"X-API-Key": "key-a"},
    )
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "tenant-a"


def test_request_validation_rejects_bad_input_with_422() -> None:
    """An input that fails the capability model is a 422."""
    client = _client()
    # validate_outcome_rule requires a yaml_text string; omitting it is invalid input.
    resp = post(client, "/validate_outcome_rule", json={}, headers={"X-API-Key": "key-a"})
    assert resp.status_code == 422


def test_webhook_rejects_malformed_body_after_signature() -> None:
    """A correctly-signed but non-JSON webhook body yields a validation error (422)."""
    client = _client()
    raw = b"not-json-at-all"
    signature = hmac.new(_WEBHOOK_SECRET, raw, hashlib.sha256).hexdigest()
    resp = post(
        client,
        "/ingest_otlp_span",
        content=raw,
        headers={"X-API-Key": "key-a", "X-Signature": signature},
    )
    # signature verifies, but the empty-parsed body fails the input model
    assert resp.status_code == 422


def test_streaming_capability_is_projected_as_sse() -> None:
    """A streaming capability is projected onto an SSE route."""
    from _api_helpers import ListNotesInput, ListNotesOutput
    from valuemaxx.capabilities import Registry, capability

    def _stream_handler(request: ListNotesInput) -> ListNotesOutput:
        return ListNotesOutput(tenant_id=request.tenant_id, notes=("streamed",))

    registry = Registry()
    registry.register(
        capability(
            name="stream_notes",
            input_model=ListNotesInput,
            output_model=ListNotesOutput,
            handler=_stream_handler,
            description="Stream the calling tenant's notes as SSE.",
            surfaces=Surface.API,
            mode=Mode.STREAMING,
        )
    )
    client = _client(registry)
    resp = post(client, "/stream_notes", json={}, headers={"X-API-Key": "key-a"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "data:" in resp.text
    assert "streamed" in resp.text


def test_build_default_app_projects_canonical_registry() -> None:
    """build_default_app projects the canonical registry's API capabilities."""
    from valuemaxx.api import build_default_app

    app = build_default_app(api_keys=_API_KEYS, webhook_secret=_WEBHOOK_SECRET)
    client = TestClient(app)
    registry = build_default_registry()
    paths = route_paths(client.app)
    for cap in registry.for_surface(Surface.API):
        assert f"/{cap.name}" in paths
