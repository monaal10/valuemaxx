"""build_app accepts an optional ASGI lifespan (startup/shutdown hook).

The assembly app (``apps/server``) opens its store and wires the persistence
runtimes on ASGI startup and disposes the engine on shutdown — so the projection's
:func:`~valuemaxx.api.app.build_app` must let the caller pass a lifespan context
manager. When none is given, behavior is unchanged (no startup/shutdown side
effects). This keeps the projection the single app-construction entrypoint.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from _api_helpers import registry_with_notes
from fastapi.testclient import TestClient
from valuemaxx.api.app import build_app

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI

_WEBHOOK_SECRET = b"shhh"


def test_lifespan_startup_and_shutdown_run() -> None:
    """test_lifespan_startup_and_shutdown_run: the passed lifespan brackets the app."""
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        events.append("startup")
        try:
            yield
        finally:
            events.append("shutdown")

    app = build_app(
        registry_with_notes(),
        api_keys={"k": "tenant-a"},
        webhook_secret=_WEBHOOK_SECRET,
        lifespan=lifespan,
    )
    with TestClient(app):
        assert events == ["startup"]
    assert events == ["startup", "shutdown"]


def test_build_app_without_lifespan_still_boots() -> None:
    """test_build_app_without_lifespan_still_boots: the lifespan arg is optional."""
    app = build_app(
        registry_with_notes(),
        api_keys={"k": "tenant-a"},
        webhook_secret=_WEBHOOK_SECRET,
    )
    with TestClient(app) as client:
        assert client.app is app
