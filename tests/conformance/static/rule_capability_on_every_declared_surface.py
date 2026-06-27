"""capability_on_every_declared_surface —
a capability missing from a surface it declares (RED; owner G4-apps).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until G4-apps turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("OMITS_CAPABILITY",)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "# api router OMITS_CAPABILITY whose surfaces include API\n"


RULE = Rule(
    name="capability_on_every_declared_surface",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="G4-apps",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
