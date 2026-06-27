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

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
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
    """Run every migration up to ``head`` against the given (sync) database URL."""
    cfg = _config(url)
    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(_sync_url(url))
    try:
        with engine.begin() as connection:

            def _do_upgrade(rev: object, _context: object) -> list[object]:
                return script._upgrade_revs("head", rev)  # type: ignore[arg-type]  # alembic private API, stable since 1.x

            with EnvironmentContext(
                cfg,
                script,
                fn=_do_upgrade,
                as_sql=False,
                destination_rev="head",
            ) as env:
                env.configure(connection=connection, target_metadata=metadata)
                env.run_migrations()
    finally:
        engine.dispose()


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
