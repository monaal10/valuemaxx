"""streaming_no_delta_sum —
a streaming path that sums message_delta usage instead of taking terminal (RED; owner CAPTURE).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until CAPTURE turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("sum(", "+=")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "total = sum(chunk.usage.cache_read for chunk in deltas)\n"


RULE = Rule(
    name="streaming_no_delta_sum",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="CAPTURE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
