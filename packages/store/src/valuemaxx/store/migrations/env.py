"""Alembic environment — wires the shared MetaData as the autogenerate target.

``target_metadata`` is :data:`valuemaxx.store.tables.metadata` (the single schema
source), so ``alembic upgrade head`` followed by ``alembic revision --autogenerate``
yields an empty diff — enforced by the ``migration_no_autogen_drift`` conformance
rule. The database URL comes from the ``VALUEMAXX_DB_URL`` env var (or alembic's
``-x db_url=...``), never from a checked-in credential.

Migrations run with a *sync* DBAPI URL (the async driver suffix is stripped) because
alembic's runner is synchronous; the application uses the async engine at runtime.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool
from valuemaxx.store.tables import metadata

config = context.config

target_metadata = metadata


def _resolve_url() -> str:
    """The migration URL: ``-x db_url=...`` > ``VALUEMAXX_DB_URL`` > ini, async-stripped."""
    x_args = context.get_x_argument(as_dictionary=True)
    url = (
        x_args.get("db_url")
        or os.environ.get("VALUEMAXX_DB_URL")
        or config.get_main_option("sqlalchemy.url")
    )
    if not url:
        raise RuntimeError(
            "no database URL: pass -x db_url=..., set VALUEMAXX_DB_URL, or set sqlalchemy.url"
        )
    # Alembic's runner is synchronous; strip the async driver so it uses the sync DBAPI.
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    """Emit migration SQL without a live connection (``alembic upgrade --sql``)."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
