"""Project the capability registry onto FastAPI routes (thin projection, §3/§4/H5).

``mount_capabilities`` iterates the registry's ``Surface.API`` capabilities and
projects each onto a route BY MODE:

* ``request_response`` -> ``POST /{name}`` whose body is the capability input model
  and whose response is the output model;
* ``async_job`` -> ``POST /{name}`` that submits a background job and returns
  ``{job_id}`` (202), plus the shared ``GET /jobs/{job_id}`` poll;
* ``webhook_inbound`` -> ``POST /{name}`` that verifies the HMAC signature over the
  RAW body before parsing, then dispatches;
* ``streaming`` -> ``POST /{name}`` that streams the result as SSE.

Every route resolves the tenant from the API key (never the body) and OVERRIDES any
``tenant_id`` in the payload with the authenticated tenant, so a caller can only ever
act on its own tenant. Nothing without the API surface is projected.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from fastapi import Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from valuemaxx.api.errors import AuthError, JobNotFoundError, WebhookSignatureError
from valuemaxx.api.webhooks import verify_signature
from valuemaxx.capabilities import Mode, Surface

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import FastAPI
    from valuemaxx.api.auth import ApiKeyAuthenticator
    from valuemaxx.api.jobs import JobStore
    from valuemaxx.capabilities import AnyCapability, Registry


def _resolve(auth: ApiKeyAuthenticator, api_key: str | None) -> str:
    try:
        return auth.resolve_tenant(api_key)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _as_dict(raw: object) -> dict[str, object]:
    """Coerce a parsed JSON value to a string-keyed dict (non-objects -> empty)."""
    if isinstance(raw, dict):
        return {str(key): value for key, value in cast("dict[object, object]", raw).items()}
    return {}


async def _request_payload(request: Request) -> dict[str, object]:
    """Read and coerce the request JSON body to a string-keyed dict."""
    return _as_dict(await request.json())


def _scope(payload: dict[str, object], tenant_id: str, cap: AnyCapability) -> dict[str, object]:
    """Override ``tenant_id`` with the authenticated tenant iff the model has the field."""
    scoped = dict(payload)
    if "tenant_id" in cap.input_model.model_fields:
        scoped["tenant_id"] = tenant_id
    return scoped


def _validate(cap: AnyCapability, payload: dict[str, object]) -> BaseModel:
    # Validate with JSON-mode semantics, not dict-mode ``model_validate``: a strict
    # capability input (StrictModel, e.g. MetricDefinition) rejects a Python ``list``
    # for a ``tuple`` field in dict mode but accepts a JSON array in JSON mode. The
    # wire payload IS JSON, so re-serializing the (tenant-scoped) dict and validating
    # via ``model_validate_json`` makes the route accept exactly what JSON can express.
    try:
        return cap.input_model.model_validate_json(json.dumps(payload))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _parse_raw(raw_body: bytes) -> dict[str, object]:
    try:
        parsed: object = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="malformed JSON body") from exc
    return _as_dict(parsed)


def _mount_request_response(app: FastAPI, cap: AnyCapability, auth: ApiKeyAuthenticator) -> None:
    async def handler(
        request: Request, x_api_key: str | None = Header(default=None)
    ) -> dict[str, object]:
        tenant_id = _resolve(auth, x_api_key)
        scoped = _scope(await _request_payload(request), tenant_id, cap)
        result = cap.handler(_validate(cap, scoped))
        return result.model_dump(mode="json")

    app.post(f"/{cap.name}", name=cap.name)(handler)


def _mount_async_job(
    app: FastAPI, cap: AnyCapability, auth: ApiKeyAuthenticator, jobs: JobStore
) -> None:
    async def submit(
        request: Request, x_api_key: str | None = Header(default=None)
    ) -> dict[str, str]:
        tenant_id = _resolve(auth, x_api_key)
        scoped = _scope(await _request_payload(request), tenant_id, cap)
        model = _validate(cap, scoped)

        def work() -> dict[str, object]:
            return cap.handler(model).model_dump(mode="json")

        return {"job_id": jobs.submit(tenant_id, work)}

    app.post(f"/{cap.name}", name=cap.name, status_code=202)(submit)


def _mount_webhook(
    app: FastAPI, cap: AnyCapability, auth: ApiKeyAuthenticator, webhook_secret: bytes
) -> None:
    async def receiver(
        request: Request,
        x_api_key: str | None = Header(default=None),
        x_signature: str | None = Header(default=None),
    ) -> dict[str, object]:
        tenant_id = _resolve(auth, x_api_key)
        raw_body = await request.body()
        try:
            verify_signature(webhook_secret, raw_body, x_signature or "")
        except WebhookSignatureError as exc:
            # Reject BEFORE parsing — the handler is never called on a bad signature.
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        scoped = _scope(_parse_raw(raw_body), tenant_id, cap)
        result = cap.handler(_validate(cap, scoped))
        return result.model_dump(mode="json")

    app.post(f"/{cap.name}", name=cap.name)(receiver)


def _mount_streaming(app: FastAPI, cap: AnyCapability, auth: ApiKeyAuthenticator) -> None:
    async def stream(
        request: Request, x_api_key: str | None = Header(default=None)
    ) -> StreamingResponse:
        tenant_id = _resolve(auth, x_api_key)
        scoped = _scope(await _request_payload(request), tenant_id, cap)
        result = cap.handler(_validate(cap, scoped))
        body = json.dumps(result.model_dump(mode="json"))

        def events() -> Iterator[str]:
            yield f"data: {body}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    app.post(f"/{cap.name}", name=cap.name)(stream)


def mount_jobs_route(app: FastAPI, auth: ApiKeyAuthenticator, jobs: JobStore) -> None:
    """Mount the shared ``GET /jobs/{job_id}`` poll route (tenant-scoped)."""

    async def poll(job_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, object]:
        tenant_id = _resolve(auth, x_api_key)
        try:
            return jobs.get(tenant_id, job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    app.get("/jobs/{job_id}", name="poll_job")(poll)


def mount_capabilities(
    app: FastAPI,
    registry: Registry,
    *,
    auth: ApiKeyAuthenticator,
    jobs: JobStore,
    webhook_secret: bytes,
) -> None:
    """Project every ``Surface.API`` capability onto a route by its mode."""
    has_async = False
    for cap in registry.for_surface(Surface.API):
        if cap.mode is Mode.REQUEST_RESPONSE:
            _mount_request_response(app, cap, auth)
        elif cap.mode is Mode.ASYNC_JOB:
            _mount_async_job(app, cap, auth, jobs)
            has_async = True
        elif cap.mode is Mode.WEBHOOK_INBOUND:
            _mount_webhook(app, cap, auth, webhook_secret)
        elif cap.mode is Mode.STREAMING:
            _mount_streaming(app, cap, auth)
    if has_async:
        mount_jobs_route(app, auth, jobs)


__all__ = ["mount_capabilities", "mount_jobs_route"]
