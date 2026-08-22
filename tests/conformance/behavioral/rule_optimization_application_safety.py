"""Optimization application stays opt-in, ramped, and fast-signal reversible."""

from __future__ import annotations

from typing import cast

from valuemaxx.core.optimization import RollbackSignal

from tests.conformance.rulebase import Rule, RuleKind


def _flags(subject: object) -> bool:
    assert isinstance(subject, tuple)
    pair = cast("tuple[object, object]", subject)
    ramp, signals = pair
    assert isinstance(ramp, tuple)
    assert isinstance(signals, tuple)
    ramp_values = cast("tuple[object, ...]", ramp)
    signal_values = cast("tuple[object, ...]", signals)
    return ramp_values != (1, 5, 25, 100) or "outcome_rate" in signal_values


def _negative_fixture() -> object:
    return ((5, 100), ("error_rate", "outcome_rate"))


def _foundation_subject() -> object:
    return ((1, 5, 25, 100), tuple(signal.value for signal in RollbackSignal))


def application_contract_is_safe() -> bool:
    """Return whether the production application contract preserves both safety gates."""
    return not _flags(_foundation_subject())


RULE = Rule(
    name="optimization_application_safety",
    kind=RuleKind.BEHAVIORAL,
    green_now=True,
    owner_task="continuous-optimization",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
