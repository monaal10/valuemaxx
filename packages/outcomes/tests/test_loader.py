"""OUT-A: load_rules — yaml.safe_load + per-expression predicate validation."""

from __future__ import annotations

import pytest
from valuemaxx.outcomes.errors import OutcomeRuleSchemaError, PredicateValidationError
from valuemaxx.outcomes.loader import load_rules
from valuemaxx.outcomes.predicate import SafePredicateValidator

_VALID_YAML = """
outcomes:
  - name: loan_funded
    match: { function: "myapp.loans.update_loan_status", when: "args.status == 'funded'" }
    value: "args.amount"
    bind:  { entity_key: "args.application_id" }
    signal: outcome_confirmed

  - name: payment_succeeded
    match: { webhook: stripe, event: "payment_intent.succeeded" }
    run_id_injection:
      sdk_call:    "stripe.PaymentIntent.create"
      inject_into: "metadata.run_id"
      webhook_event: "payment_intent.succeeded"
      extract_from:  "data.object.metadata.run_id"
    value: "data.object.amount"
    signal: outcome_confirmed
"""


class _SpyValidator:
    """Wraps the real validator and records every expression it was asked to validate."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self._inner = SafePredicateValidator()

    def validate(self, expr: str) -> None:
        self.seen.append(expr)
        self._inner.validate(expr)


def test_valid_rules_compile() -> None:
    """A valid document parses into the declared rules with their fields intact."""
    rules = load_rules(_VALID_YAML, validator=SafePredicateValidator())
    assert [r.name for r in rules] == ["loan_funded", "payment_succeeded"]

    funded = rules[0]
    assert funded.match.match_kind == "function"
    assert funded.match.target == "myapp.loans.update_loan_status"
    assert funded.value == "args.amount"
    assert funded.bind["entity_key"] == "args.application_id"
    assert funded.signal == "outcome_confirmed"

    paid = rules[1]
    assert paid.match.match_kind == "webhook"
    assert paid.run_id_injection is not None
    assert paid.run_id_injection.sdk_call == "stripe.PaymentIntent.create"
    assert paid.run_id_injection.extract_from == "data.object.metadata.run_id"


def test_loader_uses_safe_load_not_load() -> None:
    """A !!python/object payload raises (yaml.safe_load, never yaml.load)."""
    malicious = """
outcomes:
  - name: pwn
    match: !!python/object/apply:os.system ["echo hi"]
"""
    with pytest.raises(OutcomeRuleSchemaError):
        load_rules(malicious, validator=SafePredicateValidator())


def test_loader_consults_injected_validator_for_every_expression() -> None:
    """The injected validator is consulted for each when/value/bind expression."""
    spy = _SpyValidator()
    load_rules(_VALID_YAML, validator=spy)
    assert "args.status == 'funded'" in spy.seen
    assert "args.amount" in spy.seen
    assert "args.application_id" in spy.seen
    assert "data.object.amount" in spy.seen


def test_loader_rejects_eval_predicate() -> None:
    """An eval predicate is rejected via the injected validator (no_eval_in_predicate)."""
    yaml_text = """
outcomes:
  - name: evil
    match: { function: "app.f", when: "eval('1+1') == 2" }
"""
    with pytest.raises(PredicateValidationError):
        load_rules(yaml_text, validator=SafePredicateValidator())


def test_loader_rejects_dunder_predicate() -> None:
    """A dunder predicate is rejected via the injected validator."""
    yaml_text = """
outcomes:
  - name: evil
    match: { function: "app.f", when: "args.__class__ == 1" }
"""
    with pytest.raises(PredicateValidationError):
        load_rules(yaml_text, validator=SafePredicateValidator())


def test_loader_rejects_two_match_kinds() -> None:
    """A match with two kinds is a schema error (exactly one)."""
    yaml_text = """
outcomes:
  - name: bad
    match: { function: "app.f", webhook: stripe }
"""
    with pytest.raises(OutcomeRuleSchemaError):
        load_rules(yaml_text, validator=SafePredicateValidator())


def test_loader_rejects_non_mapping_top_level() -> None:
    """A top-level document that is not a mapping with 'outcomes' is rejected."""
    with pytest.raises(OutcomeRuleSchemaError):
        load_rules("- just\n- a\n- list\n", validator=SafePredicateValidator())


def test_loader_rejects_outcomes_not_a_list() -> None:
    """'outcomes' must be a list of rule mappings."""
    with pytest.raises(OutcomeRuleSchemaError):
        load_rules("outcomes: 5\n", validator=SafePredicateValidator())


def test_loader_rejects_rule_missing_name() -> None:
    """A rule without a name is a schema error."""
    yaml_text = """
outcomes:
  - match: { function: "app.f" }
"""
    with pytest.raises(OutcomeRuleSchemaError):
        load_rules(yaml_text, validator=SafePredicateValidator())


def test_loader_rejects_rule_missing_match() -> None:
    """A rule without a match block is a schema error."""
    with pytest.raises(OutcomeRuleSchemaError):
        load_rules("outcomes:\n  - name: x\n", validator=SafePredicateValidator())


def test_loader_empty_document_yields_no_rules() -> None:
    """An empty 'outcomes' list yields zero rules (not an error)."""
    assert load_rules("outcomes: []\n", validator=SafePredicateValidator()) == ()


def test_loader_rejects_non_string_value_expression() -> None:
    """A non-string 'value' expression is a schema error (must be a string expr)."""
    yaml_text = """
outcomes:
  - name: x
    match: { webhook: stripe }
    value: 12345
"""
    with pytest.raises(OutcomeRuleSchemaError, match="must be a string"):
        load_rules(yaml_text, validator=SafePredicateValidator())


def test_loader_rejects_malformed_yaml() -> None:
    """Unparseable YAML surfaces as a schema error, not a raw yaml exception."""
    with pytest.raises(OutcomeRuleSchemaError, match="parse"):
        load_rules("outcomes: [unbalanced\n", validator=SafePredicateValidator())


def test_loader_rejects_incomplete_run_id_injection() -> None:
    """A run_id_injection block missing keys is a schema error."""
    yaml_text = """
outcomes:
  - name: x
    match: { webhook: stripe }
    run_id_injection:
      sdk_call: "stripe.PaymentIntent.create"
"""
    with pytest.raises(OutcomeRuleSchemaError, match="missing keys"):
        load_rules(yaml_text, validator=SafePredicateValidator())


def test_loader_accepts_function_match_declaring_confirmed_as_preference() -> None:
    """A function match may *declare* confirmed; the mapper clamps it later (not an error)."""
    yaml_text = """
outcomes:
  - name: x
    match: { function: "app.f", when: "args.ok" }
    signal: outcome_confirmed
"""
    rules = load_rules(yaml_text, validator=SafePredicateValidator())
    # The declared preference is preserved on the rule; the emit-time mapper has final say.
    assert rules[0].signal == "outcome_confirmed"


def test_loader_rejects_invalid_declared_signal() -> None:
    """A declared signal outside the closed vocabulary is rejected."""
    yaml_text = """
outcomes:
  - name: x
    match: { webhook: stripe }
    signal: nonsense
"""
    with pytest.raises(OutcomeRuleSchemaError):
        load_rules(yaml_text, validator=SafePredicateValidator())
