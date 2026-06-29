"""Integration fixtures — a REAL Postgres via testcontainers (H2, §9).

The JSONB byte-fidelity and migration-drift checks genuinely require Postgres (SQLite
has no JSONB and a different autogenerate surface), so these run against a real
``postgres:16`` container started once per session. Each test gets a fresh schema
(migrated with ``alembic upgrade head``) so cross-test state never leaks.

Point them at an existing Postgres with ``VALUEMAXX_TEST_PG_URL`` (an asyncpg URL) to
run without Docker; otherwise they use a testcontainer where Docker exists (CI) and
skip with a clear reason where it doesn't, per the build plan's H2 rule.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from valuemaxx.store.engine import create_engine, create_sessionmaker
from valuemaxx.store.migrations_api import upgrade_to_head

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _docker_available() -> tuple[bool, str]:
    """Return (available, reason) for whether a Docker daemon can be reached.

    Probed with ``docker info`` over a subprocess (not the untyped docker SDK), so the
    gate stays strict-typed and has no stub dependency. A non-zero exit or missing
    binary means no usable daemon — the real-PG tests then skip with the captured reason.
    """
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        return False, "docker CLI not on PATH"
    try:
        proc = subprocess.run(  # fixed argv, no shell, no user input
            ["docker", "info"],  # docker resolved on PATH above
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"docker probe failed: {exc}"
    if proc.returncode != 0:
        return False, "docker daemon unavailable (docker info returned non-zero)"
    return True, ""


_DOCKER_OK, _DOCKER_REASON = _docker_available()


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A session-scoped real Postgres URL — an existing instance or a fresh container.

    Resolution order:

    1. ``VALUEMAXX_TEST_PG_URL`` (an asyncpg URL to an already-running Postgres) — lets
       these tests run without Docker (e.g. a local ``postgres`` instance), which is also
       how they were verified during development.
    2. Otherwise a ``postgres:16`` testcontainer (CI), gated on a reachable Docker daemon;
       when Docker is unavailable every dependent test SKIPS with a reason rather than
       erroring (a module-level ``pytestmark`` in a conftest does not apply to the tests,
       so the gate lives here in the shared fixture).
    """
    explicit = os.environ.get("VALUEMAXX_TEST_PG_URL")
    if explicit:
        yield explicit
        return
    if not _DOCKER_OK:
        pytest.skip(f"real-Postgres integration needs Docker (testcontainers); {_DOCKER_REASON}")
    # testcontainers ships no type stubs; the import is test-only and Docker-gated above.
    from testcontainers.postgres import (  # pyright: ignore[reportMissingTypeStubs]
        PostgresContainer,
    )

    with PostgresContainer("postgres:16", driver="asyncpg") as container:
        url = container.get_connection_url()
        assert isinstance(url, str)
        yield url


@pytest_asyncio.fixture
async def pg_sessionmaker(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A sessionmaker over the real Postgres, with a freshly migrated schema per test."""
    upgrade_to_head(postgres_url)
    engine = create_engine(postgres_url)
    try:
        yield create_sessionmaker(engine)
    finally:
        # Reset to a TRULY empty database so the next test's upgrade_to_head re-runs the
        # migration. ``metadata.drop_all`` drops the data tables but NOT alembic's
        # ``alembic_version`` bookkeeping table — leaving it stamped at head, so the next
        # ``upgrade_to_head`` would see "already at head" and create nothing
        # (``relation … does not exist``). Dropping + recreating the whole ``public``
        # schema removes every table including ``alembic_version``, guaranteeing a clean slate.
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()
