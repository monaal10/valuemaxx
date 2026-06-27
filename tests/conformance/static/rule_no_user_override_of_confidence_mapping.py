"""no_user_override_of_confidence_mapping —
a user-facing setter for the tier->label mapping (RED; owner ATTRIBUTION).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until ATTRIBUTION turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("set_confidence_mapping", "TIER_LABELS.update", "def set_tier_label")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "def set_confidence_mapping(user_map): TIER_LABELS.update(user_map)\n"


RULE = Rule(
    name="no_user_override_of_confidence_mapping",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="ATTRIBUTION",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
