"""OUT-D: inbound outcome-webhook ingest — verify BEFORE parse, T3 echo / T4 fallback.

:func:`receive_webhook` enforces a strict order (§3.2, §6.3):

1. **Verify first.** The per-source HMAC signature *and* the ingest key are checked with
   :func:`hmac.compare_digest` (constant-time) **before the body is parsed at all** — an
   attacker-controlled payload is never deserialized on an unverified request. A failure
   raises :class:`WebhookSignatureError`; the secret/ingest key never reaches a log.
2. **Parse** the JSON body (only now that it is trusted).
3. **Bind.** Extract ``run_id`` via the rule's ``extract_from`` path: present →
   ``tier=deterministic, bound_by='t3_webhook_echo'``; absent → fall through to
   ``tier=candidate, bound_by='t4_entity_pending'`` with the extracted entity keys
   (labeled, **never silently mis-bound** as deterministic).
4. **Signal** via the system :class:`~valuemaxx.core.SignalClassMapper` (webhook is
   authoritative, so a declared ``outcome_confirmed`` is honored).
5. **Idempotency** is the echoed ``run_id`` (used as the correlation id) or ``(source,id)``.

The function returns a :class:`~valuemaxx.core.WebhookResult` describing the verified,
parsed, bound outcome, and emits the :class:`~valuemaxx.core.OutcomeEvent` via the
injected emitter.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from valuemaxx.core import (
    AtmError,
    BindingTier,
    CorrelationId,
    RunId,
    WebhookResult,
)
from valuemaxx.outcomes.predicate import compile_expr
from valuemaxx.outcomes.safelog import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from valuemaxx.core import TenantId
    from valuemaxx.outcomes.instrument.emitter import OutcomeEmitter
    from valuemaxx.outcomes.schema import OutcomeRule

# How the run_id was recovered: T3 round-trip echo, or T4 entity fallback (labeled).
ExtractedVia = Literal["echo", "entity_fallback"]

_logger = get_logger("valuemaxx.outcomes.webhook")


class WebhookSignatureError(AtmError):
    """A webhook failed signature or ingest-key verification (rejected before parse)."""


@dataclass(frozen=True, slots=True)
class WebhookSecurity:
    """The per-source verification material (never logged)."""

    signing_secret: str
    ingest_key: str


@dataclass(frozen=True, slots=True)
class WebhookRequest:
    """A raw inbound webhook: the source, the exact body bytes, and the presented creds."""

    source: str
    body: bytes
    signature: str
    ingest_key: str


def receive_webhook(
    request: WebhookRequest,
    *,
    rule: OutcomeRule,
    security: WebhookSecurity,
    emitter: OutcomeEmitter,
    tenant_id: TenantId,
) -> WebhookResult:
    """Verify, parse, bind, and emit an inbound outcome webhook (verify strictly first).

    Raises:
        WebhookSignatureError: if the signature or ingest key fails verification — this
            happens *before* the body is parsed, and no secret is logged.
    """
    _verify(request, security)  # step 1 — BEFORE any parse
    payload = _parse(request.body)  # step 2 — only now
    event_type = _event_type(payload)

    declared_event = rule.match.event
    if declared_event is not None and event_type != declared_event:
        # Verified but not the event this rule cares about — acknowledge, do not emit.
        return WebhookResult(
            verified=True,
            source=request.source,
            event_type=event_type,
            run_id=None,
            extracted_via=None,
            payload=payload,
        )

    run_id, extracted_via = _extract_run_id(rule, payload)
    _emit(
        rule=rule,
        payload=payload,
        run_id=run_id,
        extracted_via=extracted_via,
        emitter=emitter,
        tenant_id=tenant_id,
        source=request.source,
    )
    return WebhookResult(
        verified=True,
        source=request.source,
        event_type=event_type,
        run_id=run_id,
        extracted_via=extracted_via,
        payload=payload,
    )


def _verify(request: WebhookRequest, security: WebhookSecurity) -> None:
    """Constant-time check of the HMAC signature AND the ingest key; raise on mismatch.

    The secret and ingest key are never included in the raised message or any log line.
    """
    expected_sig = hmac.new(
        security.signing_secret.encode(), request.body, hashlib.sha256
    ).hexdigest()
    sig_ok = hmac.compare_digest(expected_sig, request.signature)
    key_ok = hmac.compare_digest(security.ingest_key, request.ingest_key)
    if not (sig_ok and key_ok):
        _logger.warning("rejected webhook from %s: verification failed", request.source)
        raise WebhookSignatureError(f"webhook verification failed for source {request.source!r}")


def _parse(body: bytes) -> Mapping[str, object]:
    try:
        loaded: object = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookSignatureError(f"unparseable webhook body: {exc}") from exc
    if not isinstance(loaded, dict):
        raise WebhookSignatureError("webhook body must be a JSON object")
    return {str(k): v for k, v in loaded.items()}  # type: ignore[misc]  # json keys are str


def _event_type(payload: Mapping[str, object]) -> str:
    event_type = payload.get("type")
    return event_type if isinstance(event_type, str) else ""


def _extract_run_id(
    rule: OutcomeRule, payload: Mapping[str, object]
) -> tuple[RunId | None, ExtractedVia]:
    """Recover run_id via the rule's extract_from path; None when it didn't echo back."""
    injection = rule.run_id_injection
    if injection is None:
        return None, "entity_fallback"
    raw = compile_expr(injection.extract_from)({"data": payload.get("data")})
    if isinstance(raw, str) and raw:
        return RunId(raw), "echo"
    return None, "entity_fallback"


def _emit(
    *,
    rule: OutcomeRule,
    payload: Mapping[str, object],
    run_id: RunId | None,
    extracted_via: ExtractedVia,
    emitter: OutcomeEmitter,
    tenant_id: TenantId,
    source: str,
) -> None:
    from valuemaxx.outcomes.instrument.emitter import EmitRequest, coerce_money

    namespace: dict[str, object] = {"data": payload.get("data")}
    value = compile_expr(rule.value)(namespace) if rule.value is not None else None
    entity_keys = frozenset(
        (name, str(compile_expr(expr)(namespace))) for name, expr in rule.bind.items()
    )
    if extracted_via == "echo" and run_id is not None:
        # T3: the run_id round-tripped — an exact deterministic bind. Use it as the
        # dedup correlation id so a re-delivery of the same outcome never double-counts.
        tier: BindingTier | None = BindingTier.DETERMINISTIC
        bound_by: str | None = "t3_webhook_echo"
        correlation_id: CorrelationId | None = CorrelationId(run_id)
    else:
        # T4: no echo — labeled candidate, never silently mis-bound as deterministic.
        tier = BindingTier.CANDIDATE
        bound_by = "t4_entity_pending"
        correlation_id = None

    emitter.emit(
        EmitRequest(
            tenant_id=tenant_id,
            name=rule.name,
            match_kind="webhook",
            declared_signal=rule.signal,
            value=coerce_money(value),
            entity_keys=entity_keys,
            correlation_id=correlation_id,
            source=source,
            run_id=run_id,
            raw=payload,
            binding_tier=tier,
            bound_by=bound_by,
        )
    )


__all__ = [
    "WebhookRequest",
    "WebhookSecurity",
    "WebhookSignatureError",
    "receive_webhook",
]
