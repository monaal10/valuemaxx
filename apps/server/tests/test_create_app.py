"""create_app wiring edge cases — empty ingest keys leave the metrics runtime unwired.

When no ingest keys are configured there is no tenant to scope the single-tenant
``run_metric`` runtime to, so the metrics capability is left unwired (it raises a
clear ``MetricsNotWiredError`` rather than silently returning a wrong-tenant result).
The ingest runtime is always wired; the app still boots and routes still mount.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from _server_helpers import route_paths
from fastapi.testclient import TestClient
from valuemaxx.capabilities import Registry
from valuemaxx.server.app import create_app
from valuemaxx.server.settings import ServerSettings

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_create_app_with_no_ingest_keys_still_boots(tmp_path: Path) -> None:
    """test_create_app_with_no_ingest_keys_still_boots: empty keys -> metrics unwired, app boots."""
    settings = ServerSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'no-keys.db'}",
        ingest_keys={},
        webhook_secret="sec",
    )
    app = create_app(settings)
    with TestClient(app):
        paths = route_paths(app)
        assert "/ingest_otlp_span" in paths
        assert "/run_metric" in paths


def test_create_app_exposes_the_assembled_registry_on_app_state(tmp_path: Path) -> None:
    """create_app publishes the SAME assembled registry on ``app.state.registry``.

    The composition root exposes the assembled :class:`~valuemaxx.capabilities.Registry`
    so an operator/test can re-bind a capability runtime (e.g. re-point ``run_metric``
    at the store's outcomes for cost-per-outcome) against the very registry the surfaces
    project from. The definitive ``tests/e2e`` install->run->see-it-work flow depends on
    this affordance; this unit guard fails fast if it is ever dropped (ratchet §5a).
    """
    settings = ServerSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}",
        ingest_keys={"k": "00000000-0000-0000-0000-000000000001"},
        webhook_secret="sec",
    )
    app = create_app(settings)
    registry = getattr(app.state, "registry", None)
    assert isinstance(registry, Registry)
    # the published registry carries the projected capabilities (it IS the one the
    # surfaces mounted from — a fresh/empty registry would expose no run_metric).
    assert any(cap.name == "run_metric" for cap in registry.all())


def test_create_app_reads_settings_from_env_when_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """test_create_app_reads_settings_from_env_when_none: no settings arg -> env-driven."""
    db = tmp_path / "env.db"
    monkeypatch.setenv("VALUEMAXX_DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("VALUEMAXX_WEBHOOK_SECRET", "env-secret")
    app = create_app()
    with TestClient(app):
        assert "/ingest_otlp_span" in route_paths(app)
