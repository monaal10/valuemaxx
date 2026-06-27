"""candidate_likely_never_billing_grade —
code that treats a candidate/likely binding as billing-grade (RED; owner ATTRIBUTION).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until ATTRIBUTION turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("bill_as_grade", "billing_grade = True")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "if tier in (CANDIDATE, LIKELY): bill_as_grade(metric)\n"


RULE = Rule(
    name="candidate_likely_never_billing_grade",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="ATTRIBUTION",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
