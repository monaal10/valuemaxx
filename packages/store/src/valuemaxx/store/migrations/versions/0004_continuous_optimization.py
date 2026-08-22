"""Continuous-optimization artifacts and nullable gateway config stamps.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-22

The initial migration creates live MetaData, so a fresh database already contains
these additions. This revision therefore checks every table/column/index before
creating it, while still upgrading databases deployed through revision 0003.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from alembic import op
from valuemaxx.store.tables import (
    optimization_baseline,
    optimization_deployment,
    optimization_experiment,
    optimization_finding,
    optimization_frontier,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES: tuple[sa.Table, ...] = (
    optimization_baseline,
    optimization_finding,
    optimization_frontier,
    optimization_experiment,
    optimization_deployment,
)

_COST_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[Any]], ...] = (
    ("call_site_id", sa.String()),
    ("system_hash", sa.String()),
    ("tools_hash", sa.String()),
    ("params_hash", sa.String()),
    ("config_identity", sa.String()),
    ("config_identity_weak", sa.Boolean()),
    ("http_status", sa.Integer()),
)

_COST_INDEX = "ix_valuemaxx_cost_event_call_site_config"


def _has_table(bind: sa.Connection, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _has_column(bind: sa.Connection, table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _has_index(bind: sa.Connection, table: str, name: str) -> bool:
    return name in {item["name"] for item in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    """Add optimizer tables and nullable request-configuration stamp columns."""
    bind = op.get_bind()
    for table in _TABLES:
        if not _has_table(bind, table.name):
            table.create(bind=bind)

    for name, type_ in _COST_COLUMNS:
        if not _has_column(bind, "valuemaxx_cost_event", name):
            op.add_column(
                "valuemaxx_cost_event",
                sa.Column(name, type_, nullable=True),
            )
    if not _has_index(bind, "valuemaxx_cost_event", _COST_INDEX):
        op.create_index(
            _COST_INDEX,
            "valuemaxx_cost_event",
            ["tenant_id", "call_site_id", "config_identity", "occurred_at"],
        )


def downgrade() -> None:
    """Remove only revision-0004 schema additions, in dependency-safe order."""
    bind = op.get_bind()
    if _has_index(bind, "valuemaxx_cost_event", _COST_INDEX):
        op.drop_index(_COST_INDEX, table_name="valuemaxx_cost_event")
    for name, _type in reversed(_COST_COLUMNS):
        if _has_column(bind, "valuemaxx_cost_event", name):
            op.drop_column("valuemaxx_cost_event", name)
    for table in reversed(_TABLES):
        if _has_table(bind, table.name):
            table.drop(bind=bind)
