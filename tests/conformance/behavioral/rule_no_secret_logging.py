"""no_secret_logging — a sentinel key must never reach a log/span/DB (GREEN; owner OUTCOMES).

Runtime sentinel rule (NOT a static grep): a known ingest/provider key is injected, the
paths are exercised, and the rule asserts the sentinel appears in no log record.
``flags_violation`` inspects a captured-sink dump (a list of emitted strings) and flags
it iff the sentinel leaked.

The foundation subject runs the outcomes package's secret-handling path — the webhook
receiver's *verify-before-parse* rejection, where the signing secret and ingest key are
the sentinel — while capturing every log record. The receiver logs only "verification
failed" with the source, never the secret, so the sentinel never appears. (The rule is
co-owned by RECON/EVAL/ONBOARDING, which extend the exercised paths through G5; the
OUTCOMES path is green now.)
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from typing_extensions import override

from tests.conformance.rulebase import Rule, RuleKind

SENTINEL = "sk-ant-SENTINEL-do-not-log-0xDEADBEEF"


def _flags(subject: object) -> bool:
    """subject is the captured sink dump (emitted log/span/db strings)."""
    assert isinstance(subject, list)
    records = cast("list[object]", subject)
    return any(SENTINEL in str(record) for record in records)


def _negative_fixture() -> object:
    # a sink dump where a code path leaked the sentinel into a log line
    return [f"INFO using provider key {SENTINEL}", "DEBUG request sent"]


class _CapturingHandler(logging.Handler):
    """Captures every log record's rendered message into a list (the sink dump)."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.dump: list[str] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.dump.append(record.getMessage())


def _foundation_subject() -> object:
    """Run the outcomes webhook verify-rejection with the sentinel as the secret.

    Captures all logging on the root logger and returns the emitted messages. The
    sentinel is used as both the signing secret and ingest key; verification fails on a
    bad signature, and the receiver must log the rejection WITHOUT echoing the secret.
    """
    from valuemaxx.core import SignalClass, TenantId
    from valuemaxx.outcomes.instrument.emitter import OutcomeEmitter
    from valuemaxx.outcomes.repository import InMemoryOutcomeEventRepository
    from valuemaxx.outcomes.schema import MatchSpec, OutcomeRule
    from valuemaxx.outcomes.signal import SystemSignalClassMapper
    from valuemaxx.outcomes.webhook import (
        WebhookRequest,
        WebhookSecurity,
        WebhookSignatureError,
        receive_webhook,
    )

    handler = _CapturingHandler()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        emitter = OutcomeEmitter(
            repository=InMemoryOutcomeEventRepository(),
            mapper=SystemSignalClassMapper(),
            clock=_StaticClock(),
            uuid_gen=_StaticUuid(),
        )
        rule = OutcomeRule(
            name="payment_succeeded",
            match=MatchSpec(webhook="stripe", event="payment_intent.succeeded"),
            value=None,
            bind={},
            signal=SignalClass.OUTCOME_CONFIRMED.value,
        )
        request = WebhookRequest(
            source="stripe",
            body=b'{"type": "payment_intent.succeeded"}',
            signature="deadbeef-wrong-signature",
            ingest_key=SENTINEL,
        )
        # expected: a bad signature is rejected before parse (the secret never logged)
        with contextlib.suppress(WebhookSignatureError):
            receive_webhook(
                request,
                rule=rule,
                security=WebhookSecurity(signing_secret=SENTINEL, ingest_key=SENTINEL),
                emitter=emitter,
                tenant_id=TenantId(uuid4()),
            )
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
    return handler.dump


class _StaticClock:
    def now(self) -> datetime:
        return datetime(2026, 6, 27, tzinfo=UTC)


class _StaticUuid:
    def new(self) -> str:
        return "sentinel-outcome"


RULE = Rule(
    name="no_secret_logging",
    kind=RuleKind.BEHAVIORAL,
    green_now=True,
    owner_task="OUTCOMES",  # also RECON, EVAL, ONBOARDING; final at G5
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
