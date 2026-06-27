"""no_raw_source_exfil —
an onboarding path that transmits whole source files off-box (RED; owner ONBOARDING).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until ONBOARDING turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("open(", ".read()", "whole_file")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "upload(open(path).read())  # whole-file exfil\n"


RULE = Rule(
    name="no_raw_source_exfil",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="ONBOARDING",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
