"""valuemaxx.server — the runnable backend assembly (the composition root).

This app is what makes valuemaxx actually *boot*: it builds the store (running
migrations), discovers and registers every capability, injects the concrete store
repositories into the capability runtimes that persist (capture's OTLP-in and the
metrics executor), and projects the registry onto FastAPI routes via the existing
``valuemaxx.api`` projection.

Public surface:

- :func:`~valuemaxx.server.app.create_app` — build the FastAPI app from settings;
- :data:`~valuemaxx.server.app.app` — the ASGI entrypoint ``uvicorn`` serves;
- :class:`~valuemaxx.server.settings.ServerSettings` — env-driven configuration;
- :class:`~valuemaxx.server.store_bridge.StoreBridge` — the sync->async store bridge.

As an ``apps/*`` projection, this is the one place framework wiring and store
construction meet; the logic packages it composes stay framework-free.
"""

from __future__ import annotations

from valuemaxx.server.app import app, create_app
from valuemaxx.server.settings import ServerSettings
from valuemaxx.server.store_bridge import StoreBridge

__all__ = ["ServerSettings", "StoreBridge", "app", "create_app"]
