"""Test the ``python -m valuemaxx.server`` entrypoint wiring (uvicorn.run is patched).

``main()`` reads the env-configured host/port and serves ``valuemaxx.server.app:app``
with uvicorn. We patch ``uvicorn.run`` so the test asserts the wiring (the app path
+ the settings-derived host/port) without actually binding a socket.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import uvicorn
from valuemaxx.server.__main__ import main

if TYPE_CHECKING:
    import pytest


def test_main_serves_the_app_with_configured_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """test_main_serves_the_app_with_configured_host_and_port: main() wires uvicorn.run."""
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run(app: str, **kwargs: object) -> None:
        calls.append((app, kwargs))

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setenv("VALUEMAXX_PORT", "9123")

    main()

    assert len(calls) == 1
    app_path, kwargs = calls[0]
    assert app_path == "valuemaxx.server.app:app"
    assert kwargs["port"] == 9123
    assert kwargs["host"] == "127.0.0.1"
