"""STORE-1 — the migration applies and leaves no autogenerate drift.

``alembic upgrade head`` must build the full schema, and a subsequent
``--autogenerate`` against :data:`valuemaxx.store.tables.metadata` must find nothing
to do (an empty upgrade body). The real-Postgres edition of this lives in the
integration suite; this unit edition runs the same logic on SQLite so the
migration/metadata coupling is checked even when Docker is unavailable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine, inspect
from valuemaxx.store.migrations_api import autogenerate_upgrade_ops, upgrade_to_head
from valuemaxx.store.tables import metadata

if TYPE_CHECKING:
    from pathlib import Path


def test_upgrade_creates_every_table(tmp_path: Path) -> None:
    """upgrade head creates every table declared on the shared MetaData."""
    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade_to_head(url)
    engine = create_engine(url)
    try:
        present = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    for table_name in metadata.tables:
        assert table_name in present, f"{table_name} not created by the migration"


def test_autogenerate_yields_no_drift(tmp_path: Path) -> None:
    """After upgrade head, autogenerate finds no schema changes (empty diff)."""
    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade_to_head(url)
    ops = autogenerate_upgrade_ops(url)
    assert ops == [], f"autogenerate drift detected: {ops}"
