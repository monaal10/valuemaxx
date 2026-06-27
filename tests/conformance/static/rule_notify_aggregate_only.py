"""notify_aggregate_only — a digest model holding raw prompt / PII fields (RED; owner NOTIFY).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until NOTIFY turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("raw_prompt", "end_user_email", "raw_response")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "class Digest(BaseModel):\n    raw_prompt: str\n    end_user_email: str\n"


RULE = Rule(
    name="notify_aggregate_only",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="NOTIFY",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
