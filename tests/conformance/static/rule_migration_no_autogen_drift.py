"""migration_no_autogen_drift —
``alembic upgrade head`` then ``--autogenerate`` yields an empty diff (owner STORE).

STORE owns every migration; recon/alloc/metrics never autogenerate. The guarantee:
after applying the migrations the live schema matches ``valuemaxx.store.tables.metadata``
exactly, so autogenerate has nothing to emit. ``flags_violation`` scans the *rendered*
autogenerate body for a schema-changing op (``op.add_column`` / ``op.drop_column`` /
``op.alter_column`` / ``op.create_table`` / ``op.drop_table``); a body containing any of
those means drift.

The foundation subject renders the real autogenerate body: it applies the migrations to
a throwaway SQLite database and renders whatever alembic would generate. A body with no
``op.*`` (just ``pass``) is the green state. The authoritative production-dialect edition
runs on real Postgres in ``packages/store/tests/integration``; this dialect-agnostic
edition keeps the rule green wherever the suite runs, including without Docker.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.conformance.rulebase import Rule, RuleKind

_MARKERS: tuple[str, ...] = (
    "op.add_column",
    "op.drop_column",
    "op.alter_column",
    "op.create_table",
    "op.drop_table",
)


def _flags(subject: object) -> bool:
    assert isinstance(subject, str)
    return any(marker in subject for marker in _MARKERS)


def _negative_fixture() -> object:
    return "op.add_column('cost_event', sa.Column('drift', sa.Integer()))\n"


def _foundation_subject() -> object:
    from valuemaxx.store.migrations_api import render_autogenerate_body

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{Path(tmp) / 'drift.db'}"
        return render_autogenerate_body(url)


RULE = Rule(
    name="migration_no_autogen_drift",
    kind=RuleKind.STATIC,
    green_now=True,
    owner_task="STORE",
    flags_violation=_flags,
    negative_fixture=_negative_fixture,
    foundation_subject=_foundation_subject,
)
