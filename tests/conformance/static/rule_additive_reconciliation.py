"""additive_reconciliation —
a reconciliation repo exposing an update/mutate path (RED; owner RECON).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until RECON turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = ("update", "mutate", "replace", "overwrite", "patch")


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "class Repo:\n    def update_estimate(self, x): ...\n"


RULE = Rule(
    name="additive_reconciliation",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="RECON",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
