"""G1-CORE-OUTCOMES-ATTR: WebhookResult + C3 Protocols + ReviewQueue ABC."""

from __future__ import annotations

import inspect
from typing import Literal, get_args, get_type_hints

from valuemaxx.core.ids import RunId
from valuemaxx.core.repositories import ReviewQueue
from valuemaxx.core.webhook import (
    OutcomesPredicateValidator,
    SignalClassMapper,
    WebhookResult,
)


def test_webhook_result_verified_flag() -> None:
    """test_webhook_result_verified_flag: WebhookResult carries a verified flag."""
    result = WebhookResult(
        verified=True,
        source="stripe",
        event_type="payment_intent.succeeded",
        run_id=RunId("run-1"),
        extracted_via="echo",
        payload={"amount": 1000},
    )
    assert result.verified is True
    assert result.extracted_via == "echo"


def test_webhook_extracted_via_is_constrained() -> None:
    """extracted_via is a constrained Literal (echo | entity_fallback | None)."""
    hints = get_type_hints(WebhookResult)
    args = get_args(hints["extracted_via"])
    assert Literal["echo", "entity_fallback"] in args or {"echo", "entity_fallback"} <= set(args)
    result = WebhookResult(
        verified=False,
        source="salesforce",
        event_type="x",
        run_id=None,
        extracted_via=None,
        payload={},
    )
    assert result.extracted_via is None


def test_signal_mapper_protocol_runtime_checkable() -> None:
    """test_signal_mapper_protocol_runtime_checkable."""

    class _Mapper:
        def map_signal(self, *, match_kind: str, declared: str) -> str:
            return "action_attempted"

    assert isinstance(_Mapper(), SignalClassMapper)
    assert not isinstance(object(), SignalClassMapper)


def test_outcomes_predicate_validator_protocol_present() -> None:
    """test_outcomes_predicate_validator_protocol_present."""

    class _Validator:
        def validate(self, expr: str) -> None:
            return None

    assert isinstance(_Validator(), OutcomesPredicateValidator)
    assert not isinstance(object(), OutcomesPredicateValidator)


def test_review_queue_methods_tenant_first() -> None:
    """test_review_queue_methods_tenant_first: ReviewQueue ABC methods take tenant_id first."""
    abstract: frozenset[str] = getattr(ReviewQueue, "__abstractmethods__", frozenset())
    assert {"enqueue", "list_pending"} <= abstract
    for name in abstract:
        func = getattr(ReviewQueue, name)
        params = [p for p in inspect.signature(func).parameters if p != "self"]
        assert params, f"ReviewQueue.{name} has no parameters"
        assert params[0] == "tenant_id", f"ReviewQueue.{name} first param not tenant_id"
