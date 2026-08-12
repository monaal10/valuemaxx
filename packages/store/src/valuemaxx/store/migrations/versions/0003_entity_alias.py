"""valuemaxx_entity_alias — asserted identity edges between entity keys.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-12

Like 0002, this is written to be a no-op on a fresh database: 0001 builds the whole
schema from the live MetaData, so the table already exists there and creating it
again would fail. It is created only where absent, which is the deployed-before-this
-change database this revision exists for.

Purely additive — no existing table is touched and nothing is backfilled. Traffic
captured before aliasing existed had no alias, and the empty closure is the honest
representation of that: every key resolves to itself until someone asserts otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "valuemaxx_entity_alias"


def _has_table(bind: sa.Connection) -> bool:
    return _TABLE in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if _has_table(op.get_bind()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_value", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # An alias asserted twice is one claim, not two. Without this a retrying
        # sender would multiply the edges the closure walks.
        sa.UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_value",
            "target_type",
            "target_value",
            name="uq_valuemaxx_entity_alias_edge",
        ),
    )
    op.create_index(f"ix_{_TABLE}_tenant", _TABLE, ["tenant_id"])


def downgrade() -> None:
    if _has_table(op.get_bind()):
        op.drop_table(_TABLE)
