"""cost_event.latency_ms + run experiment/variant/app columns.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12

0001 builds the whole schema from the live MetaData, so a *fresh* database already
has this column and this migration would try to add it twice. It is written to be a
no-op in that case: the column is added only where it is absent, which is exactly
the deployed-before-this-change database this revision exists for.

Every column here is nullable on purpose and none is backfilled. A span from a
producer that never measured the attempt must stay distinguishable from one that
measured 0ms; traffic that ran before experiment stamping existed genuinely belongs
to no arm, and inventing one would fabricate a comparison.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDED: tuple[tuple[str, str, sa.types.TypeEngine[object]], ...] = (
    ("valuemaxx_cost_event", "latency_ms", sa.Integer()),
    ("valuemaxx_run", "experiment", sa.String()),
    ("valuemaxx_run", "variant", sa.String()),
    ("valuemaxx_run", "app", sa.String()),
)


def _has_column(bind: sa.Connection, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, type_ in _ADDED:
        if not _has_column(bind, table, column):
            op.add_column(table, sa.Column(column, type_, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, _type in reversed(_ADDED):
        if _has_column(bind, table, column):
            op.drop_column(table, column)
