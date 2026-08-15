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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID, uuid4

from fastapi import Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from valuemaxx.api.errors import AuthError, JobNotFoundError, WebhookSignatureError
from valuemaxx.api.webhooks import verify_signature
from valuemaxx.attribution.capabilities import attribution_request_scope
from valuemaxx.capabilities import Mode, Surface
from valuemaxx.capture.capabilities import IngestNotWiredError, ingest_attribute_maps
from valuemaxx.capture.otlp.collector import otlp_json_to_attribute_maps
from valuemaxx.core.alias import EntityAlias
from valuemaxx.core.ids import TenantId
from valuemaxx.metrics.capabilities import metric_tenant_scope

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from contextlib import AbstractContextManager

    from fastapi import FastAPI
    from valuemaxx.api.auth import ApiKeyAuthenticator
    from valuemaxx.api.jobs import JobStore
    from valuemaxx.capabilities import AnyCapability, Registry

    NowFn = Callable[[], datetime]

    class EntityAliasWriter(Protocol):
        """The one method the alias route needs from the store.

        Narrower than the repository on purpose: the route records a claim and never
        reads the closure back, so depending on the full repo would overstate what
        this surface can do.
        """

        async def append(self, tenant_id: TenantId, alias: EntityAlias, now: datetime) -> None: ...


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


def _tenant_scope(tenant_id: str) -> AbstractContextManager[None] | None:
    """The per-request metric tenant scope, or None if the tenant is not a UUID.

    Capabilities whose input model has no `tenant_id` field (`MetricDefinition` —
    the tenant is deliberately never trusted from the body) receive the resolved
    tenant out-of-band through this scope. Without it the metrics runtime fell back
    to one tenant chosen at startup and served it to every caller.

    A non-UUID tenant (a self-host key map may use any string) simply gets no scope
    rather than a 500: the runtime's own fallback still applies, and a malformed
    tenant must never take down capabilities that do not consult the scope at all.
    """
    try:
        return metric_tenant_scope(TenantId(UUID(tenant_id)))
    except ValueError:
        return None


def _mount_request_response(app: FastAPI, cap: AnyCapability, auth: ApiKeyAuthenticator) -> None:
    async def handler(
        request: Request, x_api_key: str | None = Header(default=None)
    ) -> dict[str, object]:
        tenant_id = _resolve(auth, x_api_key)
        scoped = _scope(await _request_payload(request), tenant_id, cap)
        validated = _validate(cap, scoped)
        # Capabilities whose input model has no `tenant_id` field (MetricDefinition —
        # the tenant is deliberately never trusted from the body) get the resolved
        # tenant out-of-band instead. Without this the metrics runtime fell back to a
        # tenant chosen at startup and served it to every caller.
        scope = _tenant_scope(tenant_id)
        if scope is None:
            result = cap.handler(validated)
        else:
            with scope:
                result = cap.handler(validated)
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


def mount_otlp_collector_route(app: FastAPI, registry: Registry, auth: ApiKeyAuthenticator) -> None:
    """Mount ``POST /v1/traces`` — the real OTLP/HTTP collector for SDK spans.

    The SDK's ``@opentelemetry/exporter-trace-otlp-http`` posts a standard OTLP-JSON
    ``ExportTraceServiceRequest`` here, authenticated with the per-tenant ingest key
    in the ``x-valuemaxx-ingest-key`` header (the OTLP exporter cannot HMAC-sign, so
    this is key-auth like every other ingest path; ``x-api-key`` is accepted as a
    fallback for non-OTLP callers). Each span's ``gen_ai.*``/``ai_margin.*``
    attributes are decoded to a flat map and persisted as a CostEvent via the bound
    capture runtime. Returns the OTLP-conventional empty ``partialSuccess`` body.
    """

    async def collect(
        request: Request,
        x_valuemaxx_ingest_key: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        tenant_id = _resolve(auth, x_valuemaxx_ingest_key or x_api_key)
        body = _parse_raw(await request.body())
        attribute_maps = otlp_json_to_attribute_maps(body)
        try:
            ingest_attribute_maps(registry, TenantId(UUID(tenant_id)), attribute_maps)
        except IngestNotWiredError as exc:
            # The collector is mounted but no persistence runtime is bound — surface
            # it loudly (503) rather than 200-acking spans we silently dropped.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # OTLP success: an empty body (no partialSuccess) means every span was accepted.
        return {}

    app.post("/v1/traces", name="otlp_collect")(collect)


def mount_jobs_route(app: FastAPI, auth: ApiKeyAuthenticator, jobs: JobStore) -> None:
    """Mount the shared ``GET /jobs/{job_id}`` poll route (tenant-scoped)."""

    async def poll(job_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, object]:
        tenant_id = _resolve(auth, x_api_key)
        try:
            return jobs.get(tenant_id, job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    app.get("/jobs/{job_id}", name="poll_job")(poll)


# Stripe's meter-event window: late REAL outcomes (a deal closing weeks later) fit
# inside 35 days; a timestamp from years past or the future is a caller clock bug,
# and silently accepting it buries the outcome in a metric window nobody queries.
_OUTCOME_MAX_AGE = timedelta(days=35)
_OUTCOME_MAX_SKEW = timedelta(minutes=5)


def _validated_occurred_at(raw: object) -> str:
    """The event timestamp to store: validated when supplied, now() otherwise."""
    if raw is None:
        return datetime.now(tz=UTC).isoformat()
    if not isinstance(raw, str):
        raise HTTPException(status_code=422, detail="occurred_at must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="occurred_at must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=422, detail="occurred_at must be timezone-aware")
    now = datetime.now(tz=UTC)
    if parsed < now - _OUTCOME_MAX_AGE or parsed > now + _OUTCOME_MAX_SKEW:
        raise HTTPException(
            status_code=422,
            detail=(
                "occurred_at outside the acceptance window (35 days back to 5 minutes forward)"
            ),
        )
    return parsed.isoformat()


def mount_outcome_alias_route(app: FastAPI, registry: Registry, auth: ApiKeyAuthenticator) -> None:
    """`POST /outcome` — the one-line outcome call, no SDK required.

    `bind_outcome` takes a full `OutcomeEvent`: ids, timestamps, signal class, binding
    envelope, honesty fields. That is the right internal contract and the wrong thing
    to hand a user writing a curl. This alias accepts the four things a caller actually
    knows — name, and one of run_id / entity keys, plus optional value and signal —
    and synthesizes the rest, so recording an outcome is one line instead of a schema
    exercise.

    The tier stays null on the way in: the backend cascade decides it and revalidates
    the run. A caller can assert what happened, never how much to trust the link.
    """
    cap = next((c for c in registry.all() if c.name == "bind_outcome"), None)
    if cap is None:  # pragma: no cover - registry always carries it
        return

    async def handler(
        request: Request,
        x_api_key: str | None = Header(default=None),
        baggage: str | None = Header(default=None),
        strict: bool = False,
    ) -> dict[str, object]:
        tenant_id = _resolve(auth, x_api_key)
        payload = await _request_payload(request)
        name = payload.get("name")
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=422, detail="'name' is required")

        run_id = payload.get("run_id")
        entity = payload.get("entity")
        occurred_at = _validated_occurred_at(payload.get("occurred_at"))
        if strict and not (isinstance(run_id, str) and run_id) and not entity:
            # Segment-style discipline, opt-in: an event with neither join key will
            # never attach to any spend, and this caller asked to be told loudly
            # rather than record a row that reads as data.
            raise HTTPException(
                status_code=422,
                detail="strict mode: one of run_id or entity is required",
            )
        entity_keys: list[list[str]] = []
        if isinstance(entity, dict):
            entity_raw = cast("dict[str, object]", entity)
            entity_keys = [[key, str(value)] for key, value in entity_raw.items()]
        # The caller's `identifier` becomes the event id, so the store's upsert is
        # the dedup: an at-least-once sender (waitUntil replay, webhook retry) that
        # repeats an identifier overwrites its own row instead of inflating the
        # denominator. No identifier keeps today's random id.
        identifier = payload.get("identifier")
        event_id = (
            f"oe_{identifier}" if isinstance(identifier, str) and identifier else f"oe_{uuid4()}"
        )
        event: dict[str, object] = {
            "tenant_id": tenant_id,
            "id": event_id,
            "name": name,
            "signal_class": payload.get("signal") or "outcome_confirmed",
            "value": payload.get("value"),
            "occurred_at": occurred_at,
            "binding": {
                "run_id": run_id if isinstance(run_id, str) and run_id else None,
                "tier": None,
                "bound_by": None,
            },
            "entity_keys": entity_keys,
            "correlation_id": payload.get("correlation_id"),
            "source": payload.get("source") or "rest",
            "raw": payload.get("raw") or {},
        }
        validated = _validate(cap, event)
        with attribution_request_scope(baggage=baggage):
            result = cap.handler(validated)
        return _with_attachment(
            result.model_dump(mode="json"),
            had_run_id=isinstance(run_id, str) and bool(run_id),
            had_entity=bool(entity_keys),
        )

    app.post("/outcome", name="outcome_alias")(handler)


def _with_attachment(
    body: dict[str, object], *, had_run_id: bool, had_entity: bool
) -> dict[str, object]:
    """Say plainly whether the event attached to any spend, and if not, why.

    The contract is already uniform — one endpoint, one body, every field but `name`
    optional. What was NOT uniform is the answer: an outcome that carried a join key
    and failed to match returned a response byte-identical to one sent with no join
    key at all. Both are a 200 with a null tier, so both read as success, and the
    orphan stays invisible until someone notices the denominator is too small weeks
    later.

    So the shape of the request never varies and the shape of the reply never varies
    either — it always carries `attached`, `attachment` and, when unattached, a
    `hint` naming what the CALLER can change. A reason the caller cannot act on is
    just a different way of saying nothing.
    """
    attached = body.get("run_id") is not None
    if attached:
        attachment = "run_id" if had_run_id else "entity"
        hint = ""
    elif had_entity:
        attachment = "entity_unmatched"
        hint = (
            "No run carried that entity key inside the binding window. Send the "
            "run_id you used on the LLM calls, or POST /v1/alias if the entity is "
            "known by a different id there."
        )
    elif had_run_id:
        attachment = "run_unmatched"
        hint = (
            "No spend was captured under that run_id. Check it matches the "
            "x-vmx-run-id sent on the LLM calls for this unit."
        )
    else:
        attachment = "none"
        hint = (
            "The event carried neither run_id nor entity, so it can never attach to "
            "spend. Send run_id (preferred) or entity. Use ?strict=true to make this "
            "a 422 instead."
        )
    return {**body, "attached": attached, "attachment": attachment, "hint": hint}


def mount_entity_alias_route(app: FastAPI, auth: ApiKeyAuthenticator, now: NowFn) -> None:
    """`POST /v1/alias` — two entity keys are the same entity.

    The hole this closes: a session that spends real money while anonymous and only
    becomes a known lead afterwards. Every span it produced carries the anonymous key,
    so an outcome naming the lead joins none of them, and the spend is orphaned.

    Aliases apply at QUERY time; nothing stored is rewritten. A span keeps recording
    what the caller actually sent, and a claim that arrives months later still re-joins
    the history it refers to.
    """

    async def handler(
        request: Request,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        tenant_id = _resolve(auth, x_api_key)
        # Resolved per request: the store opens during lifespan, after routes mount.
        aliases = cast("EntityAliasWriter | None", getattr(request.app.state, "aliases", None))
        if aliases is None:
            raise HTTPException(status_code=503, detail="alias store is not wired")
        payload = await _request_payload(request)
        source = _entity_key(payload.get("from"), "from")
        target = _entity_key(payload.get("to"), "to")
        if source == target:
            # Not an error worth failing a retry over, but recording a self-edge
            # would add a claim that says nothing.
            return {"status": "ignored", "reason": "from and to are the same key"}
        # `tenant_id` is a UUID column, not a string: the resolver returns text and the
        # store rejects it. Converted here, as every other tenant-scoped route does.
        try:
            scoped = TenantId(UUID(tenant_id))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="tenant is not a UUID") from exc
        await aliases.append(scoped, EntityAlias(source=source, target=target), now())
        return {"status": "recorded", "from": list(source), "to": list(target)}

    app.post("/v1/alias", name="entity_alias")(handler)


def _entity_key(raw: object, field: str) -> tuple[str, str]:
    """Read a `{type: value}` object as one entity key.

    Exactly one pair: an alias is a claim about ONE identity. Accepting several would
    silently assert every cross-pairing between them, which is a much larger claim
    than the caller wrote.
    """
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=422,
            detail=f"'{field}' must be an object with exactly one entity key",
        )
    pairs = cast("dict[str, object]", raw)
    if len(pairs) != 1:
        raise HTTPException(
            status_code=422,
            detail=f"'{field}' must be an object with exactly one entity key",
        )
    key, value = next(iter(pairs.items()))
    if not key or value is None or str(value) == "":
        raise HTTPException(status_code=422, detail=f"'{field}' has an empty entity key")
    return (key, str(value))


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
    # The OTLP/HTTP collector is a fixed transport route (not a capability projection):
    # the SDK's exporter posts raw OTLP-JSON, which has no capability input model.
    mount_otlp_collector_route(app, registry, auth)
    mount_outcome_alias_route(app, registry, auth)
    mount_entity_alias_route(app, auth, lambda: datetime.now(UTC))


__all__ = [
    "mount_capabilities",
    "mount_entity_alias_route",
    "mount_jobs_route",
    "mount_otlp_collector_route",
]
