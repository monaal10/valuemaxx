"""granularity_labeled — a CostEvent emit path missing capture_granularity (RED; owner CAPTURE).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until CAPTURE turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("MISSING_capture_granularity",)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "emit_cost_event(tokens=tv, provider=p, MISSING_capture_granularity=True)\n"


RULE = Rule(
    name="granularity_labeled",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="CAPTURE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
