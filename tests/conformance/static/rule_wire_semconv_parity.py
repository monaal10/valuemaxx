"""wire_semconv_parity — a Py/TS OTLP key-set mismatch (RED; owner OTLP-CONTRACT).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until OTLP-CONTRACT turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("PROMPT", "COMPLETION")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "gen_ai.usage.PROMPT_tokens\n"


RULE = Rule(
    name="wire_semconv_parity",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="OTLP-CONTRACT",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
