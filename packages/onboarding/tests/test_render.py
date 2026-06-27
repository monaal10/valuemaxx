"""Tests for RENDER — deterministic YAML/markdown rendering of a proposal."""

from __future__ import annotations

import yaml
from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.onboarding.capabilities import (
    OutcomeRuleCandidate,
    Proposal,
    RunIdInjection,
)
from valuemaxx.onboarding.render import (
    render_agents_md_snippet,
    render_outcomes_yaml,
    render_shared_costs_yaml,
)


def _rule(**kw: object) -> OutcomeRuleCandidate:
    base: dict[str, object] = {
        "name": "ticket_resolved",
        "match_kind": "status_setter",
        "match_target": "app.py:mark_resolved",
        "when": "args.status == 'resolved'",
        "signal": SignalClass.OUTCOME_CONFIRMED,
        "tier": BindingTier.EXACT,
    }
    base.update(kw)
    return OutcomeRuleCandidate.model_validate(base)


def _proposal(*rules: OutcomeRuleCandidate) -> Proposal:
    return Proposal(rules=rules, entity_ids=("ticket_id",), warnings=())


def test_render_outcomes_yaml_is_deterministic() -> None:
    proposal = _proposal(_rule(name="b_rule"), _rule(name="a_rule"))
    first = render_outcomes_yaml(proposal)
    second = render_outcomes_yaml(proposal)
    assert first == second


def test_render_outcomes_yaml_round_trips_via_safe_load() -> None:
    proposal = _proposal(_rule())
    rendered = render_outcomes_yaml(proposal)
    loaded = yaml.safe_load(rendered)
    assert loaded["outcomes"][0]["name"] == "ticket_resolved"
    assert loaded["outcomes"][0]["signal"] == "outcome_confirmed"


def test_render_outcomes_yaml_sorts_rules_by_name() -> None:
    proposal = _proposal(_rule(name="zzz"), _rule(name="aaa"))
    loaded = yaml.safe_load(render_outcomes_yaml(proposal))
    names = [o["name"] for o in loaded["outcomes"]]
    assert names == sorted(names)


def test_render_outcomes_yaml_has_no_timestamp() -> None:
    rendered = render_outcomes_yaml(_proposal(_rule()))
    lowered = rendered.lower()
    assert "generated_at" not in lowered
    assert "timestamp" not in lowered


def test_render_includes_run_id_injection_block_for_t3() -> None:
    rule = _rule(
        name="charge",
        match_kind="external_write",
        signal=SignalClass.ACTION_ATTEMPTED,
        tier=BindingTier.DETERMINISTIC,
        run_id_injection=RunIdInjection(
            system="stripe",
            target_field="metadata.atm_run_id",
            write_site="app.billing.charge",
        ),
    )
    loaded = yaml.safe_load(render_outcomes_yaml(_proposal(rule)))
    inj = loaded["outcomes"][0]["run_id_injection"]
    assert inj["system"] == "stripe"
    assert inj["target_field"] == "metadata.atm_run_id"


def test_render_shared_costs_returns_none_when_no_inputs() -> None:
    proposal = _proposal(_rule())  # shared_costs_present defaults False
    assert render_shared_costs_yaml(proposal) is None


def test_render_shared_costs_returns_yaml_when_present() -> None:
    proposal = Proposal(
        rules=(_rule(),), entity_ids=(), shared_costs_present=True, warnings=()
    )
    rendered = render_shared_costs_yaml(proposal)
    assert rendered is not None
    assert yaml.safe_load(rendered) is not None


def test_render_outcomes_yaml_contains_no_secret() -> None:
    leak = "args.key == 'sk-ant-api03-RENDERLEAK0123456789abcdefghij'"
    rendered = render_outcomes_yaml(_proposal(_rule(when=leak)))
    assert "sk-ant-api03-RENDERLEAK0123456789abcdefghij" not in rendered


def test_render_agents_md_snippet_mentions_outcomes() -> None:
    snippet = render_agents_md_snippet(_proposal(_rule()))
    assert "outcomes.yaml" in snippet
    assert "ticket_resolved" in snippet
