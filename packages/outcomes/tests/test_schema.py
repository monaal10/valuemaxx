"""OUT-A: the outcome-rule schema (frozen dataclasses, not pydantic domain types)."""

from __future__ import annotations

import dataclasses

import pytest
from valuemaxx.outcomes.errors import OutcomeRuleSchemaError
from valuemaxx.outcomes.schema import MatchSpec, OutcomeRule, RunIdInjectionSpec


def test_match_spec_exactly_one_kind() -> None:
    """A MatchSpec must declare exactly one match kind, exposed as match_kind."""
    spec = MatchSpec(function="myapp.loans.update_loan_status", when="args.status == 'funded'")
    assert spec.match_kind == "function"
    assert spec.target == "myapp.loans.update_loan_status"


def test_match_spec_rejects_zero_kinds() -> None:
    """Zero match kinds is a schema error."""
    with pytest.raises(OutcomeRuleSchemaError, match="exactly one"):
        MatchSpec(when="args.ok")


def test_match_spec_rejects_two_kinds() -> None:
    """Two match kinds is a schema error (exactly one)."""
    with pytest.raises(OutcomeRuleSchemaError, match="exactly one"):
        MatchSpec(function="a.b", http="POST /x", when="args.ok")


def test_match_spec_webhook_carries_event() -> None:
    """A webhook match carries the source as target and the event separately."""
    spec = MatchSpec(webhook="stripe", event="payment_intent.succeeded")
    assert spec.match_kind == "webhook"
    assert spec.target == "stripe"
    assert spec.event == "payment_intent.succeeded"


def test_all_five_match_kinds_supported() -> None:
    """function, http, orm_save, status_transition, webhook are all valid kinds."""
    assert MatchSpec(function="a.b").match_kind == "function"
    assert MatchSpec(http="POST /pay").match_kind == "http"
    assert MatchSpec(orm_save="app.models.Loan").match_kind == "orm_save"
    assert MatchSpec(status_transition="app.Ticket.status").match_kind == "status_transition"
    assert MatchSpec(webhook="stripe").match_kind == "webhook"


def test_run_id_injection_spec_round_trips_its_fields() -> None:
    """RunIdInjectionSpec holds the four declared fields verbatim."""
    spec = RunIdInjectionSpec(
        sdk_call="stripe.PaymentIntent.create",
        inject_into="metadata.run_id",
        webhook_event="payment_intent.succeeded",
        extract_from="data.object.metadata.run_id",
    )
    assert spec.sdk_call == "stripe.PaymentIntent.create"
    assert spec.inject_into == "metadata.run_id"
    assert spec.webhook_event == "payment_intent.succeeded"
    assert spec.extract_from == "data.object.metadata.run_id"


def test_outcome_rule_holds_all_fields() -> None:
    """OutcomeRule carries name, match, value, bind, run_id_injection, signal."""
    rule = OutcomeRule(
        name="loan_funded",
        match=MatchSpec(function="myapp.loans.update", when="args.status == 'funded'"),
        value="args.amount",
        bind={"entity_key": "args.application_id"},
        signal="outcome_confirmed",
        run_id_injection=None,
    )
    assert rule.name == "loan_funded"
    assert rule.match.match_kind == "function"
    assert rule.value == "args.amount"
    assert rule.bind["entity_key"] == "args.application_id"
    assert rule.signal == "outcome_confirmed"


def test_schema_objects_are_frozen() -> None:
    """The schema dataclasses are immutable (frozen)."""
    spec = MatchSpec(function="a.b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.function = "c.d"  # type: ignore[misc]


def test_schema_classes_are_not_pydantic_models() -> None:
    """The schema is dataclasses, not pydantic domain models (no_type_outside_core)."""
    for cls in (MatchSpec, OutcomeRule, RunIdInjectionSpec):
        assert dataclasses.is_dataclass(cls)
        assert not hasattr(cls, "model_validate")
