"""resolver_emits_only_its_own_tier —
a resolver emitting a candidate with a foreign tier (RED; owner ATTRIBUTION).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until ATTRIBUTION turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("FOREIGN_TIER",)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "return AttributionCandidate(tier=FOREIGN_TIER)  # in a LIKELY resolver\n"


RULE = Rule(
    name="resolver_emits_only_its_own_tier",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="ATTRIBUTION",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
