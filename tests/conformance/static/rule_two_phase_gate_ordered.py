"""two_phase_gate_ordered — a phase-2 cost gate invoked before phase-1 approval (RED; owner EVAL).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until EVAL turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("run_confirmation_set(",)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "run_confirmation_set()  # no smoke_approved guard\n"


RULE = Rule(
    name="two_phase_gate_ordered",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="EVAL",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
