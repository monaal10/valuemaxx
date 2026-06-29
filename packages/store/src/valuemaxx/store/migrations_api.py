"""Programmatic alembic driver — upgrade + autogenerate-diff, no shell required.

These wrap alembic's Python API so the migration set can be exercised from tests
(and the ``migration_no_autogen_drift`` conformance rule) without shelling out.
:func:`upgrade_to_head` runs every migration; :func:`autogenerate_upgrade_ops`
compares the live schema against :data:`valuemaxx.store.tables.metadata` and returns
the list of operations alembic *would* generate — an empty list means no drift.

URLs are sync DBAPI URLs (alembic's runner is synchronous); the async driver suffix
is stripped if present, mirroring ``env.py``.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from valuemaxx.store.tables import metadata

# The package root holds alembic.ini and the migrations/ tree.
_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _PACKAGE_ROOT / "alembic.ini"
_SCRIPT_LOCATION = Path(__file__).resolve().parent / "migrations"


def _sync_url(url: str) -> str:
    """Strip the async driver suffix so alembic's sync runner can connect."""
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")


def _config(url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", _sync_url(url))
    return cfg


def upgrade_to_head(url: str) -> None:
    """Run every migration up to ``head`` against the given (sync) database URL.

    Uses alembic's official ``command.upgrade``, which loads ``env.py`` and runs
    ``run_migrations_online`` — that path opens a connection, configures the context,
    and wraps the run in ``context.begin_transaction()`` so the DDL is COMMITTED. (A
    previous hand-rolled ``EnvironmentContext`` runner worked on SQLite, which
    auto-commits DDL, but on Postgres the DDL transaction was never committed, so the
    tables vanished — ``relation … does not exist`` in the integration tests.)
    """
    command.upgrade(_config(url), "head")


def autogenerate_upgrade_ops(url: str) -> list[object]:
    """Return the operations autogenerate would emit against the live schema.

    An empty list means the live schema (after ``upgrade head``) matches the model
    exactly — the ``migration_no_autogen_drift`` guarantee.
    """
    engine = create_engine(_sync_url(url))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection=connection,
                opts={"compare_type": True, "target_metadata": metadata},
            )
            return list(compare_metadata(context, metadata))
    finally:
        engine.dispose()


__all__ = ["autogenerate_upgrade_ops", "upgrade_to_head"]


def render_autogenerate_body(url: str) -> str:
    """Upgrade a fresh DB to head, then render the autogenerate diff as a string.

    An **empty string** means the migration set is in sync with
    :data:`valuemaxx.store.tables.metadata` (no drift). Any non-empty body is the
    set of operations alembic would emit — i.e. real drift. Used by the
    ``migration_no_autogen_drift`` conformance rule.
    """
    upgrade_to_head(url)
    ops = autogenerate_upgrade_ops(url)
    return "\n".join(repr(op) for op in ops)
