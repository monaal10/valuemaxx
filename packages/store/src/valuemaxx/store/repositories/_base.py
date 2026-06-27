"""Shared repository scaffolding — async session ownership + dialect-aware upsert.

Every concrete repository takes an ``async_sessionmaker`` and owns one unit of work
per operation (``async with self._sessions.begin()``), so a tenant-scoped read and an
idempotent write are each atomic.

:func:`upsert_stmt` builds an INSERT ... ON CONFLICT DO UPDATE for the active dialect.
Postgres and SQLite both support the clause but expose it through *dialect-specific*
``insert`` constructors, so the helper dispatches on the bind's dialect name and falls
back to a plain INSERT for any dialect without native upsert. The conflict target is
the column set that carries the idempotency key, so at-least-once ingest replays land
on the same row rather than duplicating (M7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy import RowMapping, Table
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.sql.dml import Insert


def as_row(mapping: RowMapping) -> dict[str, object]:
    """Convert a SQLAlchemy ``RowMapping`` to the plain ``dict[str, object]`` mappers take.

    ``RowMapping`` keys are typed invariantly, so it is not assignable to
    ``Mapping[str, object]``; the mappers want a column-name-keyed dict. One conversion
    point keeps that coercion out of every repository.
    """
    return {str(key): mapping[key] for key in mapping.keys()}  # noqa: SIM118  # RowMapping needs .keys()


class BaseRepository:
    """Holds the sessionmaker every concrete repository operation borrows from."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Store the sessionmaker that scopes each operation's unit of work."""
        self._sessions = sessions


def upsert_stmt(
    session: AsyncSession,
    table: Table,
    values: Mapping[str, object],
    conflict_columns: Sequence[str],
) -> Insert:
    """Build an INSERT ... ON CONFLICT DO UPDATE for the session's dialect (M7).

    On conflict over ``conflict_columns`` every non-conflict column is overwritten
    with the incoming value, so a redelivery updates in place instead of erroring or
    duplicating. Dialects without native upsert get a plain INSERT.
    """
    dialect = session.bind.dialect.name
    update_cols = {c: values[c] for c in values if c not in conflict_columns}
    if dialect == "postgresql":
        pg_stmt = pg_insert(table).values(**values)
        return pg_stmt.on_conflict_do_update(
            index_elements=list(conflict_columns),
            set_=update_cols,
        )
    if dialect == "sqlite":
        sqlite_stmt = sqlite_insert(table).values(**values)
        return sqlite_stmt.on_conflict_do_update(
            index_elements=list(conflict_columns),
            set_=update_cols,
        )
    return table.insert().values(**values)


__all__ = ["BaseRepository", "as_row", "upsert_stmt"]
