"""migration_no_autogen_drift —
an alembic autogenerate that yields a non-empty diff (RED; owner STORE).

Authored RED-but-meaningful: ``flags_violation`` flags the negative fixture (a
synthetic violation source), proving the rule logic is real. The foundation
assertion is skip-marked until STORE turns it green; ``foundation_subject`` is
None until then (the meta-test only checks the negative fixture for not-yet-green
rules).
"""

from __future__ import annotations

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = (
    "op.add_column",
    "op.drop_column",
    "op.alter_column",
    "op.create_table",
)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "op.add_column('cost_event', sa.Column('drift', sa.Integer()))\n"


RULE = Rule(
    name="migration_no_autogen_drift",
    kind=RuleKind.STATIC,
    green_now=False,
    owner_task="STORE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=None,
)
