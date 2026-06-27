"""CLI app tests — every CLI capability is a command; rollups print minimum_tier.

The CLI is a thin projection: each ``Surface.CLI`` capability becomes a typer
command, and the three scaffolder commands (``init``/``up``/``onboard``) are always
present. A rollup-returning command always prints ``minimum_tier`` (H7) and the
distribution; a command requires ``--tenant``.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING
from uuid import uuid4

from _cli_helpers import post_json, route_paths
from typer.testing import CliRunner
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.capabilities import Surface
from valuemaxx.cli.main import build_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    import typer
    from fastapi import FastAPI

_runner = CliRunner()


def _command_names(app: typer.Typer) -> set[str]:
    """The set of registered command names (deriving the typer default for None)."""
    names: set[str] = set()
    for command in app.registered_commands:
        name = command.name
        callback = command.callback
        if isinstance(name, str):
            names.add(name)
        elif callback is not None:
            names.add(callback.__name__)
    return names


def test_scaffolder_commands_exist() -> None:
    """init / up / onboard are registered commands."""
    app = build_app()
    assert {"init", "up", "onboard"} <= _command_names(app)


def test_every_cli_capability_is_a_command() -> None:
    """Each Surface.CLI capability is projected as a command (hyphenated name)."""
    app = build_app()
    commands = _command_names(app)
    registry = build_default_registry()
    for cap in registry.for_surface(Surface.CLI):
        assert cap.name.replace("_", "-") in commands


def test_rollup_command_prints_minimum_tier() -> None:
    """A rollup-returning command prints minimum_tier + the distribution (H7)."""
    app = build_app()
    tenant = str(uuid4())
    result = _runner.invoke(
        app,
        [
            "allocated-cost-rollup",
            "--tenant",
            tenant,
            "--json-input",
            json.dumps(
                {
                    "tenant_id": tenant,
                    "run_id": "run-1",
                    "measured_costs": ["10.00"],
                    "shared_costs_yaml": "",
                    "weights": {},
                    "total_true_cost_estimate": "10.00",
                }
            ),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "minimum_tier" in result.stdout
    assert "confidence_distribution" in result.stdout


def test_rollup_command_requires_tenant() -> None:
    """A capability command without --tenant errors (no untenanted invocation)."""
    app = build_app()
    result = _runner.invoke(
        app,
        ["allocated-cost-rollup", "--json-input", "{}"],
    )
    assert result.exit_code != 0


def test_non_rollup_command_runs_and_injects_tenant() -> None:
    """A non-rollup command runs; an absent tenant_id in --json-input is injected."""
    app = build_app()
    result = _runner.invoke(
        app, ["list-cost-sources", "--tenant", "tenant-a", "--json-input", "{}"]
    )
    assert result.exit_code == 0, result.stdout
    # non-rollup output: no minimum_tier headline, just the payload
    assert "minimum_tier" not in result.stdout
    assert "sources" in result.stdout


def test_init_command_runs() -> None:
    """`valuemaxx init` scaffolds (stub): detects framework + reports the init plan."""
    app = build_app()
    result = _runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "valuemaxx" in result.stdout.lower()


def test_init_detects_framework_from_marker(tmp_path: Path) -> None:
    """init detects a framework when its marker file is present in --repo."""
    (tmp_path / "manage.py").write_text("# django marker\n")
    app = build_app()
    result = _runner.invoke(app, ["init", "--repo", str(tmp_path)])
    assert result.exit_code == 0
    assert "django" in result.stdout


def test_init_emits_a_reviewable_diff_without_writing(tmp_path: Path) -> None:
    """init emits a unified diff injecting valuemaxx.init() and does NOT touch the file."""
    entry = tmp_path / "main.py"
    original = "import os\n\n\ndef create_app() -> None:\n    pass\n"
    entry.write_text(original)
    app = build_app()
    result = _runner.invoke(app, ["init", "--repo", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    # a reviewable unified diff with the injected init() call
    assert "--- " in result.stdout
    assert "+++ " in result.stdout
    assert "valuemaxx.init(" in result.stdout
    assert result.stdout.count("\n+") >= 1  # additive hunk lines
    # default is review-only: the entry file is unchanged
    assert entry.read_text() == original


def test_init_apply_writes_the_scaffold(tmp_path: Path) -> None:
    """init --apply injects the wiring into the detected entry file (reversible)."""
    entry = tmp_path / "main.py"
    original = "import os\n\n\ndef create_app() -> None:\n    pass\n"
    entry.write_text(original)
    app = build_app()
    result = _runner.invoke(app, ["init", "--repo", str(tmp_path), "--apply"])
    assert result.exit_code == 0, result.stdout
    written = entry.read_text()
    assert written != original
    assert "valuemaxx.init(" in written
    assert original in written  # additive: original body preserved


def test_init_on_already_scaffolded_entry_reports_no_changes(tmp_path: Path) -> None:
    """init on an entry that already carries the wiring reports no changes (idempotent)."""
    entry = tmp_path / "main.py"
    entry.write_text("def create_app() -> None:\n    pass\n")
    app = build_app()
    # apply once, then a review-only run sees no diff
    applied = _runner.invoke(app, ["init", "--repo", str(tmp_path), "--apply"])
    assert applied.exit_code == 0, applied.stdout
    result = _runner.invoke(app, ["init", "--repo", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert "already scaffolded" in result.stdout
    assert "+++ " not in result.stdout  # no diff emitted


def test_init_unknown_framework_emits_no_diff(tmp_path: Path) -> None:
    """init on a repo with no known entrypoint reports unknown and writes nothing."""
    app = build_app()
    result = _runner.invoke(app, ["init", "--repo", str(tmp_path)])
    assert result.exit_code == 0
    assert "unknown" in result.stdout
    assert not list(tmp_path.iterdir())  # nothing scaffolded


def test_up_command_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """`valuemaxx up` starts the assembly app and prints the served URL (serve patched)."""
    served: dict[str, object] = {}

    def _capture(app_obj: object, *, host: str, port: int) -> None:
        served["app"] = app_obj
        served["host"] = host
        served["port"] = port

    # reach the SUBMODULE via sys.modules: the package re-exports a `main` function
    # that shadows the `main` submodule attribute, so `valuemaxx.cli.main` (by attr)
    # resolves to the function, not the module.
    cli_main = sys.modules["valuemaxx.cli.main"]
    monkeypatch.setattr(cli_main, "_serve", _capture)
    app = build_app()
    result = _runner.invoke(app, ["up", "--host", "127.0.0.1", "--port", "8123"])
    assert result.exit_code == 0, result.stdout
    assert "http://127.0.0.1:8123" in result.stdout
    assert served["host"] == "127.0.0.1"
    assert served["port"] == 8123


def test_up_serves_the_real_assembly_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """up builds the create_app assembly and serves it; a TestClient hits a mounted route."""
    from fastapi.testclient import TestClient

    captured: dict[str, FastAPI] = {}

    def _capture(app_obj: FastAPI, *, host: str, port: int) -> None:
        _ = (host, port)
        captured["app"] = app_obj

    cli_main = sys.modules["valuemaxx.cli.main"]
    monkeypatch.setattr(cli_main, "_serve", _capture)
    db = tmp_path / "up.db"
    app = build_app()
    result = _runner.invoke(
        app,
        ["up", "--db", f"sqlite+aiosqlite:///{db}", "--host", "127.0.0.1", "--port", "8200"],
    )
    assert result.exit_code == 0, result.stdout
    served_app = captured["app"]
    # it is the real assembly app: routes are mounted (store opens on startup smoke)
    assert "/ingest_otlp_span" in route_paths(served_app)
    with TestClient(served_app) as client:
        # the app boots (lifespan runs migrations) — a request reaches the projection
        resp = post_json(client, "/run_metric", {})
        assert resp.status_code in {401, 403, 422}  # auth/validation, not a 404/500 mount error


def test_up_honors_database_url_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """up reads DATABASE_URL from the env when --db is not given."""
    from fastapi import FastAPI

    captured: dict[str, str] = {}

    def _capture(app_obj: object, *, host: str, port: int) -> None:
        _ = (app_obj, host, port)

    def _fake_create_app(settings: object) -> FastAPI:
        captured["database_url"] = getattr(settings, "database_url", "")
        return FastAPI()

    cli_main = sys.modules["valuemaxx.cli.main"]
    monkeypatch.setattr(cli_main, "_serve", _capture)
    monkeypatch.setattr(cli_main, "create_app", _fake_create_app)
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'env.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    app = build_app()
    result = _runner.invoke(app, ["up"])
    assert result.exit_code == 0, result.stdout
    assert captured["database_url"] == db_url


def test_onboard_command_runs() -> None:
    """`valuemaxx onboard` invokes the onboarding flow (stub reports the steps)."""
    app = build_app()
    result = _runner.invoke(app, ["onboard"])
    assert result.exit_code == 0
    assert "onboard" in result.stdout.lower()


def test_onboard_prints_proposal_and_diff_from_a_fixture_repo(tmp_path: Path) -> None:
    """onboard scans a fixture repo and prints the outcomes.yaml proposal + reviewable diff."""
    (tmp_path / "svc.py").write_text(
        "import anthropic\n\n\n"
        "def handle(ticket_id: str) -> None:\n"
        "    client = anthropic.Anthropic()\n"
        "    client.messages.create(model='m', messages=[])\n"
        "    ticket.status = 'resolved'\n"
        "    db.save()\n"
    )
    app = build_app()
    result = _runner.invoke(app, ["onboard", "--repo", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    # the rendered outcomes.yaml from the real onboarding pipeline
    assert "version: 1" in result.stdout
    assert "outcomes:" in result.stdout
    # the reviewable diff carries the injected init() at the run boundary
    assert "outcomes.yaml" in result.stdout
    assert "valuemaxx.init()" in result.stdout
    # UNCONFIRMED until human review
    assert "unconfirmed" in result.stdout.lower()


def test_onboard_empty_repo_proposes_nothing_but_does_not_crash(tmp_path: Path) -> None:
    """onboard on a repo with no outcome sites still renders a (empty) proposal."""
    app = build_app()
    result = _runner.invoke(app, ["onboard", "--repo", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert "version: 1" in result.stdout


def test_main_invokes_the_typer_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """the console-script entry point delegates to the assembled typer app."""
    from valuemaxx.cli.main import main as cli_entry

    calls: list[bool] = []
    cli_main = sys.modules["valuemaxx.cli.main"]
    monkeypatch.setattr(cli_main, "app", lambda: calls.append(True))
    cli_entry()
    assert calls == [True]
