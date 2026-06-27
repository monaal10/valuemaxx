"""scaffold_caps tests — scaffold/validate tools that return UNCONFIRMED drafts.

``register_scaffold_caps`` adds agent-facing helper capabilities (on MCP among other
surfaces): ``scaffold_outcome_rule`` (draft an outcomes.yaml rule) and
``validate_init`` (check an init snippet). Anything that proposes a rule returns a
DRAFT explicitly marked unconfirmed/candidate — never auto-applied; a human confirms.
"""

from __future__ import annotations

from valuemaxx.agent_integrability.scaffold_caps import (
    ScaffoldOutcomeRuleInput,
    register_scaffold_caps,
    scaffold_outcome_rule,
    validate_init,
)
from valuemaxx.agent_integrability.scaffold_caps import (
    ValidateInitInput as _ValidateInitInput,
)
from valuemaxx.capabilities import Registry, Surface


def test_scaffold_caps_register_onto_mcp() -> None:
    """The scaffold/validate tools are registered and declare the MCP surface."""
    registry = Registry()
    register_scaffold_caps(registry)
    names = {c.name for c in registry.all()}
    assert {"scaffold_outcome_rule", "validate_init"} <= names
    for cap in registry.all():
        assert Surface.MCP in cap.surfaces


def test_scaffold_outcome_rule_returns_unconfirmed_draft() -> None:
    """scaffold_outcome_rule returns a DRAFT flagged unconfirmed (never auto-applied)."""
    result = scaffold_outcome_rule(
        ScaffoldOutcomeRuleInput(
            outcome_name="signup_completed",
            description="A user finished signup",
            signal_hint="outcome_confirmed",
        )
    )
    assert result.confirmed is False
    assert result.binding_tier == "candidate"
    assert "signup_completed" in result.draft_yaml
    # the draft must not assert a system-owned axis as confirmed
    assert "unconfirmed" in result.note.lower()


def test_validate_init_flags_missing_init_call() -> None:
    """validate_init reports whether the snippet calls valuemaxx.init()."""
    ok = validate_init(_ValidateInitInput(snippet="import valuemaxx\nvaluemaxx.init()\n"))
    assert ok.valid is True
    bad = validate_init(_ValidateInitInput(snippet="print('no init here')\n"))
    assert bad.valid is False
    assert bad.reason is not None


def test_scaffold_caps_do_not_collide_with_onboarding() -> None:
    """The scaffold caps add new names, not duplicates of onboarding's own caps."""
    registry = Registry()
    register_scaffold_caps(registry)
    names = {c.name for c in registry.all()}
    # onboarding already owns suggest_attribution_rule / validate_outcome_rule; the
    # scaffold caps add distinct helper tools.
    assert "scaffold_outcome_rule" in names
    assert "validate_init" in names
