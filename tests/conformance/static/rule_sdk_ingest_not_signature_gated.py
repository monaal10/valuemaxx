"""sdk_ingest_not_signature_gated — the SDK OTLP ingest path is key-auth, never signed.

A real SDK ships spans through a standard OTLP exporter authenticated with ONLY the
per-tenant ingest key (``X-API-Key``); it CANNOT HMAC-sign the OTLP body. The API
projection routes a ``webhook_inbound`` capability through a signature-required
receiver (``_mount_webhook`` verifies an HMAC over the raw body before parse). So a
producer-side ingest capability that an SDK exporter calls MUST NOT be
``webhook_inbound`` — if it were, every real exporter's spans would be 401'd (the
exact bug this rule pins).

HMAC signing belongs on EXTERNAL inbound webhooks (Stripe/CRM outcome callbacks —
``ingest_webhook_outcome``), where the caller is a third party that cannot use your
ingest key. Those stay ``webhook_inbound``.

This rule computes the set of SDK-producer ingest capabilities (the OTLP-in path the
SDK exporter posts to) that are signature-gated. The foundation report is empty
(``ingest_otlp_span`` is ``request_response``); the negative fixture is a non-empty
report (a synthetic OTLP-in capability declared ``webhook_inbound``), which the rule
flags. If anyone regresses ``ingest_otlp_span`` to a signed webhook, this turns RED.
"""

from __future__ import annotations

from typing import cast

from tests.conformance.rulebase import Rule, RuleKind

# The SDK-producer ingest capabilities: the OTLP-in path a real OTLP exporter POSTs to
# with key-auth only. (``ingest_webhook_outcome`` is NOT here — it is an EXTERNAL
# third-party webhook that legitimately stays signature-gated.)
_SDK_INGEST_CAPABILITIES: frozenset[str] = frozenset({"ingest_otlp_span"})


def signature_gated_sdk_ingest() -> list[str]:
    """Every SDK-producer ingest capability that is signature-gated (empty = clean)."""
    from valuemaxx.agent_integrability.discovery import build_default_registry
    from valuemaxx.capabilities import Mode

    registry = build_default_registry()
    offenders: list[str] = []
    for cap in registry.all():
        if cap.name in _SDK_INGEST_CAPABILITIES and cap.mode is Mode.WEBHOOK_INBOUND:
            offenders.append(
                f"{cap.name}: SDK OTLP ingest path is webhook_inbound (signature-gated); "
                f"a real OTLP exporter sends only the ingest key and cannot HMAC-sign — "
                f"it must be request_response (key-auth)"
            )
    return offenders


def _flags(subject: object) -> bool:
    # A real report (list) is a violation iff it is non-empty.
    assert isinstance(subject, list)
    return len(cast("list[object]", subject)) > 0


def _negative_fixture() -> object:
    # A synthetic non-empty report: an OTLP-in ingest capability declared signature-gated.
    return ["ingest_otlp_span: SDK OTLP ingest path is webhook_inbound (signature-gated)"]


def _foundation_subject() -> object:
    return signature_gated_sdk_ingest()


RULE = Rule(
    name="sdk_ingest_not_signature_gated",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="foundation",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
