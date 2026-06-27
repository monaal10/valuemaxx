"""no_eval_in_predicate — a predicate/metric DSL using eval/exec/dunder (RED; owner OUTCOMES).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until OUTCOMES turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("eval(", "exec(", "__import__", "__globals__")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "eval(user_predicate)\n"


RULE = Rule(
    name="no_eval_in_predicate",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="OUTCOMES",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
