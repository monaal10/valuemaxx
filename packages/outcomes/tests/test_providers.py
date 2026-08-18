"""Shipped provider templates — the mapping from a raw webhook body to our tuple.

The receiver (`webhook.py`) was already built: verify-before-parse, run-id extraction,
entity fallback. What did not exist was the per-source layer that knows a Stripe
`checkout.session.completed` puts its id at `data.object.metadata.vmx_run_id` and its
money at `data.object.amount_total`. Without it every user reverse-engineers the same
five paths from provider docs.

These tests pin the contract a NEW template must satisfy, so adding the sixth provider
is filling in a file rather than reading this package's source.
"""

from __future__ import annotations

import pytest
from valuemaxx.outcomes.providers import PROVIDERS, load_provider_rules


def test_every_shipped_provider_parses_through_the_real_loader() -> None:
    """A template that does not load is worse than no template.

    They ship as data, so nothing at import time proves they are valid — exactly how a
    plausible-looking rule reaches a user and fails at the first webhook. Running each
    through the same loader the product uses is the only check that means anything.
    """
    assert PROVIDERS, "expected at least one shipped provider"

    for name in PROVIDERS:
        rules = load_provider_rules(name)
        assert rules, f"{name} declares no rules"


def test_each_rule_can_recover_a_run_id_or_says_it_cannot() -> None:
    """A rule that binds nothing produces an outcome no cost can ever attach to.

    That is the silent failure this whole product exists to prevent: the event is
    recorded, the reply is a 200, and the denominator quietly excludes it.
    """
    for name in PROVIDERS:
        for rule in load_provider_rules(name):
            has_echo = rule.run_id_injection is not None
            has_entity = bool(rule.bind)
            assert has_echo or has_entity, f"{name}/{rule.name} can never bind to a run"


def test_a_money_outcome_extracts_its_value() -> None:
    """Revenue is what turns cost-per-outcome into margin-per-outcome.

    A payment template that drops `value` silently downgrades the product's headline
    number for everyone who uses it.
    """
    # Keyed on the EVENT, not the outcome name: several rules share one outcome name
    # (a refund names the same outcome it later retracts), and only the events that
    # actually move money carry an amount.
    money_events = {"checkout.session.completed", "invoice.paid"}
    rules = [r for r in load_provider_rules("stripe") if r.match.event in money_events]

    assert len(rules) == len(money_events), "expected one rule per revenue event"
    assert all(r.value for r in rules)


def test_no_template_declares_a_retraction() -> None:
    """Retraction is a later flip, never a class a rule asserts.

    A refunded payment must leave the denominator — but that transition belongs to
    `retract_outcome`, which flips an outcome that was genuinely confirmed first. A
    rule declaring `outcome_retracted` up front would be claiming a state change it
    never observed, and the schema rejects it. Templates must respect that, so this
    guards against a contributor "fixing" a refund rule by asserting the class.
    """
    for name in PROVIDERS:
        for rule in load_provider_rules(name):
            assert rule.signal != "outcome_retracted", f"{name}/{rule.name}"


def test_an_unknown_provider_names_the_ones_that_exist() -> None:
    """The error a user hits on a typo should hand them the answer."""
    with pytest.raises(KeyError) as exc:
        load_provider_rules("hubspt")

    assert "stripe" in str(exc.value)


def test_the_readme_example_actually_parses() -> None:
    """A doc example that does not load is worse than no example.

    It is the first YAML anyone copies, and a rule that fails only at the first live
    webhook wastes exactly the trust the walkthrough was meant to build. This caught a
    real one: the README abbreviated `run_id_injection` to the two fields that read as
    interesting and dropped the two the schema requires.
    """
    import re
    from pathlib import Path

    from valuemaxx.outcomes.loader import load_rules
    from valuemaxx.outcomes.predicate import SafePredicateValidator

    readme = Path(__file__).resolve().parents[3] / "README.md"
    block = re.search(r"```yaml\n# valuemaxx\.outcomes\.yaml\n(.*?)```", readme.read_text(), re.S)
    assert block, "the README's outcomes.yaml example moved or was removed"

    rules = load_rules(block.group(1), validator=SafePredicateValidator())

    assert rules, "the example declares no rules"
    assert rules[0].value, "the example should show a revenue outcome"
