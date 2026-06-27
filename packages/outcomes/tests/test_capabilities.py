"""OUT-E: register(registry) adds the three outcome capabilities (+ their handlers)."""

from __future__ import annotations

import pytest
from valuemaxx.capabilities import DuplicateCapabilityError, Mode, Registry, Surface
from valuemaxx.outcomes.capabilities import (
    IngestWebhookOutcomeRequest,
    ListOutcomeRulesRequest,
    ValidateOutcomeRuleRequest,
    ingest_webhook_outcome_handler,
    list_outcome_rules_handler,
    register,
    validate_outcome_rule_handler,
)

_VALID_YAML = """
outcomes:
  - name: loan_funded
    match: { function: "myapp.loans.update", when: "args.status == 'funded'" }
    value: "args.amount"
    signal: outcome_confirmed
"""

_EVAL_YAML = """
outcomes:
  - name: evil
    match: { function: "app.f", when: "eval('1+1') == 2" }
"""


def _registered() -> Registry:
    registry = Registry()
    register(registry)
    return registry


def test_register_adds_all_three_capabilities() -> None:
    """register adds ingest_webhook_outcome, validate_outcome_rule, list_outcome_rules."""
    names = {spec.name for spec in _registered().all()}
    assert {
        "ingest_webhook_outcome",
        "validate_outcome_rule",
        "list_outcome_rules",
    } <= names


def test_ingest_capability_is_webhook_inbound_api_only() -> None:
    """ingest_webhook_outcome is a webhook_inbound capability on the API surface."""
    spec = next(s for s in _registered().all() if s.name == "ingest_webhook_outcome")
    assert spec.mode is Mode.WEBHOOK_INBOUND
    assert Surface.API in spec.surfaces
    assert Surface.CLI not in spec.surfaces  # an inbound webhook is not a CLI command


def test_validate_and_list_are_request_response_on_api_mcp_cli() -> None:
    """validate/list are request_response on API|MCP|CLI."""
    by_name = {s.name: s for s in _registered().all()}
    for name in ("validate_outcome_rule", "list_outcome_rules"):
        spec = by_name[name]
        assert spec.mode is Mode.REQUEST_RESPONSE
        assert Surface.API in spec.surfaces
        assert Surface.MCP in spec.surfaces
        assert Surface.CLI in spec.surfaces


def test_validate_handler_accepts_a_valid_rule() -> None:
    """The validate handler reports ok for a safe rule document."""
    result = validate_outcome_rule_handler(ValidateOutcomeRuleRequest(yaml_text=_VALID_YAML))
    assert result.ok is True
    assert result.rule_count == 1
    assert result.error is None


def test_validate_handler_rejects_eval_predicate() -> None:
    """The validate handler rejects an eval predicate (no_eval_in_predicate)."""
    result = validate_outcome_rule_handler(ValidateOutcomeRuleRequest(yaml_text=_EVAL_YAML))
    assert result.ok is False
    assert result.error is not None
    # the rejection is reported as a disallowed construct, not silently accepted
    assert "disallowed" in result.error.lower()


def test_validate_capability_is_wired_to_a_handler() -> None:
    """The registered validate spec carries a callable handler."""
    spec = next(s for s in _registered().all() if s.name == "validate_outcome_rule")
    assert callable(spec.handler)


def test_list_handler_returns_rule_summaries() -> None:
    """The list handler returns one summary per declared rule (name + match kind)."""
    result = list_outcome_rules_handler(ListOutcomeRulesRequest(yaml_text=_VALID_YAML))
    assert [r.name for r in result.rules] == ["loan_funded"]
    assert result.rules[0].match_kind == "function"
    assert result.rules[0].signal == "outcome_confirmed"


def test_list_handler_reports_parse_error_without_crashing() -> None:
    """A bad document yields an empty rule list + an error (handler never raises)."""
    result = list_outcome_rules_handler(ListOutcomeRulesRequest(yaml_text="outcomes: 5\n"))
    assert result.rules == []
    assert result.error is not None


def test_ingest_handler_describes_contract() -> None:
    """The ingest descriptor handler returns the unverified contract shape (no secret)."""
    result = ingest_webhook_outcome_handler(
        IngestWebhookOutcomeRequest(source="stripe", body=b"{}", signature="x", ingest_key="y")
    )
    assert result.verified is False
    assert result.accepted is False
    assert result.extracted_via is None


def test_register_is_idempotent_guarded_by_registry() -> None:
    """Registering twice into the same registry raises (no silent duplicate)."""
    registry = Registry()
    register(registry)
    with pytest.raises(DuplicateCapabilityError):
        register(registry)
