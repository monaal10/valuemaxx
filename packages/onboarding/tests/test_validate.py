"""Tests for VALIDATE — checking a proposed rule against the core Protocols."""

from __future__ import annotations

import _onboarding_helpers
import pytest
from valuemaxx.core import BindingTier, SignalClass
from valuemaxx.onboarding.capabilities import OutcomeRuleCandidate
from valuemaxx.onboarding.errors import UnsafePredicateError
from valuemaxx.onboarding.validate import validate_rule


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


def test_validate_accepts_safe_comparison() -> None:
    validate_rule(
        _rule(when="args.status == 'resolved'"),
        predicate_validator=_onboarding_helpers.StubPredicateValidator(),
        signal_mapper=_onboarding_helpers.StubSignalMapper(),
    )  # must not raise


def test_validate_rejects_eval_predicate() -> None:
    with pytest.raises(UnsafePredicateError):
        validate_rule(
            _rule(when="__import__('os').system('rm -rf /')"),
            predicate_validator=_onboarding_helpers.StubPredicateValidator(),
            signal_mapper=_onboarding_helpers.StubSignalMapper(),
        )


def test_validate_rejects_dunder_access() -> None:
    with pytest.raises(UnsafePredicateError):
        validate_rule(
            _rule(when="args.__class__"),
            predicate_validator=_onboarding_helpers.StubPredicateValidator(),
            signal_mapper=_onboarding_helpers.StubSignalMapper(),
        )


def test_validate_rejects_signal_mismatch_with_system_mapping() -> None:
    # an external_write site is system-mapped to action_attempted; a rule claiming
    # outcome_confirmed there is a tampered signal and must be rejected.
    with pytest.raises(UnsafePredicateError, match="signal"):
        validate_rule(
            _rule(
                match_kind="external_write",
                signal=SignalClass.OUTCOME_CONFIRMED,
                tier=BindingTier.CANDIDATE,
                when="True",
            ),
            predicate_validator=_onboarding_helpers.StubPredicateValidator(),
            signal_mapper=_onboarding_helpers.StubSignalMapper(),
        )


def test_validate_accepts_correctly_mapped_external_write() -> None:
    validate_rule(
        _rule(
            match_kind="external_write",
            signal=SignalClass.ACTION_ATTEMPTED,
            tier=BindingTier.CANDIDATE,
            when="True",
        ),
        predicate_validator=_onboarding_helpers.StubPredicateValidator(),
        signal_mapper=_onboarding_helpers.StubSignalMapper(),
    )  # must not raise
