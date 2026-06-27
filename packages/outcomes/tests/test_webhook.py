"""OUT-D: receive_webhook — verify (signature + ingest key) BEFORE parse, echo/fallback bind."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from valuemaxx.core import BindingTier, SignalClass, TenantId
from valuemaxx.outcomes.instrument.emitter import OutcomeEmitter
from valuemaxx.outcomes.repository import InMemoryOutcomeEventRepository
from valuemaxx.outcomes.schema import MatchSpec, OutcomeRule, RunIdInjectionSpec
from valuemaxx.outcomes.signal import SystemSignalClassMapper
from valuemaxx.outcomes.webhook import (
    WebhookRequest,
    WebhookSecurity,
    WebhookSignatureError,
    receive_webhook,
)

_TENANT = TenantId(uuid4())
_SIGNING_SECRET = "whsec_TESTSIGNINGSECRET0123456789"
_INGEST_KEY = "ingest_TESTINGESTKEY0123456789"


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 6, 27, tzinfo=UTC)


class _SeqUuid:
    def __init__(self) -> None:
        self._n = 0

    def new(self) -> str:
        self._n += 1
        return f"o-{self._n}"


def _emitter(repo: InMemoryOutcomeEventRepository) -> OutcomeEmitter:
    return OutcomeEmitter(
        repository=repo,
        mapper=SystemSignalClassMapper(),
        clock=_FixedClock(),
        uuid_gen=_SeqUuid(),
    )


def _rule() -> OutcomeRule:
    return OutcomeRule(
        name="payment_succeeded",
        match=MatchSpec(webhook="stripe", event="payment_intent.succeeded"),
        value="data.object.amount",
        bind={"customer_id": "data.object.customer"},
        signal=SignalClass.OUTCOME_CONFIRMED.value,
        run_id_injection=RunIdInjectionSpec(
            sdk_call="stripe.PaymentIntent.create",
            inject_into="metadata.run_id",
            webhook_event="payment_intent.succeeded",
            extract_from="data.object.metadata.run_id",
        ),
    )


def _security() -> WebhookSecurity:
    return WebhookSecurity(signing_secret=_SIGNING_SECRET, ingest_key=_INGEST_KEY)


def _sign(body: bytes) -> str:
    return hmac.new(_SIGNING_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _body(*, with_echo: bool = True, amount: int = 1000) -> bytes:
    obj: dict[str, object] = {"amount": amount, "customer": "cus_42"}
    if with_echo:
        obj["metadata"] = {"run_id": "run-echo-7"}
    payload = {"type": "payment_intent.succeeded", "data": {"object": obj}}
    return json.dumps(payload).encode()


def _request(
    body: bytes, *, signature: str | None = None, ingest_key: str = _INGEST_KEY
) -> WebhookRequest:
    return WebhookRequest(
        source="stripe",
        body=body,
        signature=_sign(body) if signature is None else signature,
        ingest_key=ingest_key,
    )


def test_t3_echo_binds_deterministic() -> None:
    """A verified webhook whose run_id echoes back binds deterministically (t3)."""
    repo = InMemoryOutcomeEventRepository()
    result = receive_webhook(
        _request(_body(with_echo=True)),
        rule=_rule(),
        security=_security(),
        emitter=_emitter(repo),
        tenant_id=_TENANT,
    )
    assert result.verified is True
    assert result.extracted_via == "echo"
    assert result.run_id == "run-echo-7"
    event = repo.all_for_tenant(_TENANT)[0]
    assert event.binding.run_id == "run-echo-7"
    assert event.binding.tier is BindingTier.DETERMINISTIC
    assert event.binding.bound_by == "t3_webhook_echo"
    assert event.signal_class is SignalClass.OUTCOME_CONFIRMED
    assert event.value == Decimal("1000")


def test_no_echo_falls_to_t4_candidate_labeled() -> None:
    """A verified webhook with no echoed run_id falls back to t4 candidate (labeled)."""
    repo = InMemoryOutcomeEventRepository()
    result = receive_webhook(
        _request(_body(with_echo=False)),
        rule=_rule(),
        security=_security(),
        emitter=_emitter(repo),
        tenant_id=_TENANT,
    )
    assert result.verified is True
    assert result.extracted_via == "entity_fallback"
    assert result.run_id is None
    event = repo.all_for_tenant(_TENANT)[0]
    assert event.binding.run_id is None
    assert event.binding.tier is BindingTier.CANDIDATE
    assert event.binding.bound_by == "t4_entity_pending"
    # entity keys are carried so a later entity match can bind it
    assert ("customer_id", "cus_42") in event.entity_keys


def test_unverified_signature_rejected_before_parse() -> None:
    """A bad signature raises before any parse; nothing is emitted."""
    repo = InMemoryOutcomeEventRepository()
    with pytest.raises(WebhookSignatureError):
        receive_webhook(
            _request(_body(), signature="deadbeef"),
            rule=_rule(),
            security=_security(),
            emitter=_emitter(repo),
            tenant_id=_TENANT,
        )
    assert repo.all_for_tenant(_TENANT) == ()


def test_bad_ingest_key_rejected_before_parse() -> None:
    """A bad ingest key raises before parse; nothing is emitted."""
    repo = InMemoryOutcomeEventRepository()
    with pytest.raises(WebhookSignatureError):
        receive_webhook(
            _request(_body(), ingest_key="ingest_WRONGWRONGWRONG0000"),
            rule=_rule(),
            security=_security(),
            emitter=_emitter(repo),
            tenant_id=_TENANT,
        )
    assert repo.all_for_tenant(_TENANT) == ()


def test_secret_never_logged_on_rejection(caplog: pytest.LogCaptureFixture) -> None:
    """On a verification failure, neither secret nor ingest key appears in any log."""
    repo = InMemoryOutcomeEventRepository()
    with caplog.at_level(logging.DEBUG), pytest.raises(WebhookSignatureError):
        receive_webhook(
            _request(_body(), signature="deadbeef"),
            rule=_rule(),
            security=_security(),
            emitter=_emitter(repo),
            tenant_id=_TENANT,
        )
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert _SIGNING_SECRET not in joined
    assert _INGEST_KEY not in joined


def test_idempotent_on_double_delivery() -> None:
    """Re-delivering the same echoed run_id outcome stores exactly one event."""
    repo = InMemoryOutcomeEventRepository()
    emitter = _emitter(repo)
    for _ in range(2):
        receive_webhook(
            _request(_body(with_echo=True)),
            rule=_rule(),
            security=_security(),
            emitter=emitter,
            tenant_id=_TENANT,
        )
    assert len(repo.all_for_tenant(_TENANT)) == 1


def test_signature_compare_is_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signature verification uses hmac.compare_digest (constant-time), not ==."""
    calls: list[tuple[str, str]] = []
    real = hmac.compare_digest

    def _spy(a: object, b: object) -> bool:
        if isinstance(a, str) and isinstance(b, str):
            calls.append((a, b))
        return real(a, b)  # type: ignore[arg-type]  # spy forwards to the real impl

    monkeypatch.setattr(hmac, "compare_digest", _spy)
    repo = InMemoryOutcomeEventRepository()
    receive_webhook(
        _request(_body()),
        rule=_rule(),
        security=_security(),
        emitter=_emitter(repo),
        tenant_id=_TENANT,
    )
    assert calls, "expected hmac.compare_digest to be used for verification"


def test_unparseable_verified_body_rejected() -> None:
    """A verified-but-unparseable body raises after verification (never a half-emit)."""
    repo = InMemoryOutcomeEventRepository()
    body = b"\xff\xfe not json"
    with pytest.raises(WebhookSignatureError, match="unparseable"):
        receive_webhook(
            _request(body),
            rule=_rule(),
            security=_security(),
            emitter=_emitter(repo),
            tenant_id=_TENANT,
        )
    assert repo.all_for_tenant(_TENANT) == ()


def test_non_object_json_body_rejected() -> None:
    """A verified body that is a JSON array (not an object) is rejected."""
    repo = InMemoryOutcomeEventRepository()
    body = json.dumps([1, 2, 3]).encode()
    with pytest.raises(WebhookSignatureError, match="JSON object"):
        receive_webhook(
            _request(body),
            rule=_rule(),
            security=_security(),
            emitter=_emitter(repo),
            tenant_id=_TENANT,
        )


def test_rule_without_injection_falls_back_to_entity() -> None:
    """A webhook rule with no run_id_injection block always falls to entity_fallback."""
    repo = InMemoryOutcomeEventRepository()
    rule = OutcomeRule(
        name="payment_succeeded",
        match=MatchSpec(webhook="stripe", event="payment_intent.succeeded"),
        value="data.object.amount",
        bind={"customer_id": "data.object.customer"},
        signal=SignalClass.OUTCOME_CONFIRMED.value,
        run_id_injection=None,
    )
    result = receive_webhook(
        _request(_body(with_echo=True)),
        rule=rule,
        security=_security(),
        emitter=_emitter(repo),
        tenant_id=_TENANT,
    )
    assert result.extracted_via == "entity_fallback"
    assert repo.all_for_tenant(_TENANT)[0].binding.tier is BindingTier.CANDIDATE


def test_wrong_event_type_is_not_emitted() -> None:
    """A webhook whose event type does not match the rule's event is ignored."""
    repo = InMemoryOutcomeEventRepository()
    payload = {"type": "charge.refunded", "data": {"object": {"amount": 1}}}
    body = json.dumps(payload).encode()
    result = receive_webhook(
        _request(body),
        rule=_rule(),
        security=_security(),
        emitter=_emitter(repo),
        tenant_id=_TENANT,
    )
    assert result.verified is True
    assert repo.all_for_tenant(_TENANT) == ()
