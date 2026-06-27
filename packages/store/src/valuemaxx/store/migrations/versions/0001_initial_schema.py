"""initial schema — all valuemaxx.store tables (STORE-1).

Revision ID: 0001
Revises:
Create Date: 2026-06-27

The initial migration creates the *entire* schema directly from the shared
:data:`valuemaxx.store.tables.metadata`. Driving DDL straight off the same MetaData
that alembic uses as ``target_metadata`` is what guarantees the
``migration_no_autogen_drift`` invariant: after ``upgrade head`` the live schema is
byte-identical to the model, so ``--autogenerate`` finds nothing to do. There is no
hand-transcribed column list to drift out of sync with ``tables.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op
from valuemaxx.store.tables import metadata

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create every table + index from the shared MetaData."""
    metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop every table from the shared MetaData (reverse dependency order)."""
    metadata.drop_all(bind=op.get_bind())
