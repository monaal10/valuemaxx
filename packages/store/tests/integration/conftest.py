"""Integration fixtures — a REAL Postgres via testcontainers (H2, §9).

The JSONB byte-fidelity and migration-drift checks genuinely require Postgres (SQLite
has no JSONB and a different autogenerate surface), so these run against a real
``postgres:16`` container started once per session. Each test gets a fresh schema
(migrated with ``alembic upgrade head``) so cross-test state never leaks.

If Docker is unavailable the whole module is skipped with a clear reason — the tests
are still implemented and run wherever Docker exists (CI), per the build plan's H2 rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from valuemaxx.store.engine import create_engine, create_sessionmaker
from valuemaxx.store.migrations_api import upgrade_to_head
from valuemaxx.store.tables import metadata

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
    """A session-scoped real Postgres container; yields its asyncpg URL.

    A module-level ``pytestmark`` in a *conftest* does not apply to the tests, so the
    Docker gate lives here in the shared fixture: when Docker is unavailable every
    dependent test skips (with a reason), rather than erroring. The tests are still
    implemented and run wherever Docker exists (CI), per the build plan's H2 rule.
    """
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
        # Drop the schema so the next test re-migrates onto a clean database.
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()
