"""The conformance meta-suite — wires every rule module into pytest collection.

For every declared rule this asserts:
  * the negative fixture IS flagged (proves the rule logic is real — RED rules are
    meaningful, not empty);
  * for foundation-green rules, the real foundation subject is NOT flagged (the
    rule passes against the built foundation today);
  * for not-yet-owned rules, the foundation assertion is skip-marked with the
    owning task id (never silently xfailed / never silently empty).

Plus the named meta-tests from the build plan (§F0-CONFORMANCE-SKELETON).
"""

from __future__ import annotations

import pytest

from tests.conformance.loader import all_rules
from tests.conformance.rulebase import Rule, RuleKind

_RULES = all_rules()
_IDS = [r.name for r in _RULES]


def test_rules_were_discovered() -> None:
    """Collection is non-empty — the harness is wired, not silently empty."""
    assert _RULES, "no conformance rules discovered"
    # the full §3 rule list (25 static + 4 behavioral = 29 rules)
    assert len(_RULES) == 29, f"expected 29 rules, found {len(_RULES)}: {_IDS}"


@pytest.mark.conformance
@pytest.mark.parametrize("rule", _RULES, ids=_IDS)
def test_each_rule_flags_its_negative_fixture(rule: Rule) -> None:
    """test_each_rule_flags_its_negative_fixture: every rule flags its synthetic violation."""
    fixture = rule.negative_fixture()
    assert rule.flags_violation(fixture) is True, (
        f"rule {rule.name!r} did not flag its own negative fixture"
    )


@pytest.mark.conformance
@pytest.mark.parametrize("rule", _RULES, ids=_IDS)
def test_foundation_passing_rules_green(rule: Rule) -> None:
    """test_foundation_passing_rules_green: green rules accept the foundation subject.

    Not-yet-owned rules are skip-marked with their owning task id (never silently
    xfailed) — they remain RED-but-meaningful via the negative-fixture test above.
    """
    if not rule.green_now:
        pytest.skip(f"{rule.name}: foundation-pass owned by {rule.owner_task}")
    assert rule.foundation_subject is not None, (
        f"green rule {rule.name!r} must provide a foundation_subject"
    )
    subject = rule.foundation_subject()
    assert rule.flags_violation(subject) is False, (
        f"rule {rule.name!r} wrongly flags the clean foundation subject"
    )


def test_static_behavioral_split() -> None:
    """test_static_behavioral_split: every rule is classified static or behavioral."""
    for rule in _RULES:
        assert rule.kind in (RuleKind.STATIC, RuleKind.BEHAVIORAL)
    behavioral = {r.name for r in _RULES if r.kind is RuleKind.BEHAVIORAL}
    # the behavioral (runtime, sentinel-driven) rules per §3
    assert behavioral == {
        "no_secret_logging",
        "sdk_fails_open",
        "honesty_axes_invariants",
        "otlp_collector_wire_roundtrips",
    }


def test_no_rule_is_silently_xfailed() -> None:
    """Every not-green rule names a real owning task id (never an empty owner)."""
    for rule in _RULES:
        assert rule.owner_task, f"rule {rule.name!r} has no owner_task"
        if not rule.green_now:
            assert rule.owner_task != "foundation", (
                f"rule {rule.name!r} is not green but claims the foundation owns it"
            )


def test_full_rule_list_present() -> None:
    """The complete §3 rule list (by name) is present — none dropped."""
    expected = {
        # static
        "no_type_outside_core",
        "no_logic_to_surface_import",
        "dependency_direction",
        "no_tiktoken_for_cost",
        "tenant_scoping",
        "additive_reconciliation",
        "migration_no_autogen_drift",
        "wire_semconv_parity",
        "granularity_labeled",
        "streaming_no_delta_sum",
        "resolver_emits_only_its_own_tier",
        "candidate_likely_never_billing_grade",
        "no_user_override_of_confidence_mapping",
        "grade_cap_invariant",
        "no_auto_switch",
        "two_phase_gate_ordered",
        "smoke_no_ci_confirm_requires_ci",
        "no_eval_in_predicate",
        "no_raw_source_exfil",
        "notify_aggregate_only",
        "honesty_provenance_set",
        "signal_class_never_user_set",
        "rollup_carries_confidence",
        "capability_on_every_declared_surface",
        "sdk_ingest_not_signature_gated",
        # behavioral
        "no_secret_logging",
        "sdk_fails_open",
        "honesty_axes_invariants",
        "otlp_collector_wire_roundtrips",
    }
    actual = {r.name for r in _RULES}
    assert actual == expected, f"missing: {expected - actual}; extra: {actual - expected}"


@pytest.mark.conformance
def test_no_secret_logging_is_runtime_sentinel() -> None:
    """test_no_secret_logging_is_runtime_sentinel: it is behavioral, not a static grep."""
    rule = next(r for r in _RULES if r.name == "no_secret_logging")
    assert rule.kind is RuleKind.BEHAVIORAL


def test_foundation_substantive_assertions() -> None:
    """The foundation-green rules' substantive scans pass against the real tree."""
    from tests.conformance.static import (
        rule_dependency_direction,
        rule_no_tiktoken_for_cost,
        rule_no_type_outside_core,
    )

    assert rule_no_type_outside_core.foundation_has_no_stray_domain_models() == []
    assert rule_dependency_direction.foundation_logic_cross_imports() == {}
    assert rule_no_tiktoken_for_cost.foundation_tiktoken_imports() == []


def test_honesty_axes_invariants_all_raise() -> None:
    """The behavioral honesty rule's catalogued illegal states all raise."""
    from tests.conformance.behavioral import rule_honesty_axes_invariants

    assert rule_honesty_axes_invariants.all_illegal_states_raise() is True


def test_metrics_owned_rules_green() -> None:
    """METRICS upholds the two rules it owns: no eval in the DSL, cells carry H7.

    The metric mini-DSL/compiler contain no eval/exec/dunder markers, and the
    metric result cell carries both H7 fields (minimum_tier + distribution).
    """
    from tests.conformance.static import (
        rule_no_eval_in_predicate,
        rule_rollup_carries_confidence,
    )

    assert rule_no_eval_in_predicate.metrics_dsl_has_no_eval() == []
    assert rule_rollup_carries_confidence.metrics_cell_carries_confidence() is True
