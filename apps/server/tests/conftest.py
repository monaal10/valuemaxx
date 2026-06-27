"""Fixtures for the assembly-app e2e tests — a booted app over a temp SQLite store.

The fixtures build a real :func:`~valuemaxx.server.app.create_app` against a fresh
file-based SQLite database (migrations run on startup), with two ingest keys mapped
to two distinct tenant UUIDs so cross-tenant isolation can be exercised through the
real wire path. The TestClient context manager drives the ASGI lifespan, so the
store opens on entry and is disposed on exit.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).parent))  # bare `import _server_helpers` — §5b

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from _server_helpers import KEY_A, KEY_B, WEBHOOK_SECRET
from fastapi.testclient import TestClient
from valuemaxx.server.app import create_app
from valuemaxx.server.settings import ServerSettings

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def tenant_a() -> str:
    """The UUID-string tenant bound to ``KEY_A`` (the metrics-runtime scope)."""
    return str(uuid4())


@pytest.fixture
def tenant_b() -> str:
    """The UUID-string tenant bound to ``KEY_B`` (a second, isolated tenant)."""
    return str(uuid4())


@pytest.fixture
def settings(tmp_path: object, tenant_a: str, tenant_b: str) -> ServerSettings:
    """Server settings over a fresh temp SQLite DB with two key->tenant mappings."""
    db_path = _Path(str(tmp_path)) / "e2e.db"
    return ServerSettings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        ingest_keys={KEY_A: tenant_a, KEY_B: tenant_b},
        webhook_secret=WEBHOOK_SECRET.decode("utf-8"),
    )


@pytest.fixture
def client(settings: ServerSettings) -> Iterator[TestClient]:
    """A booted TestClient — lifespan runs migrations + wires the store on entry."""
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
