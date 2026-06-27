"""CLI app tests — every CLI capability is a command; rollups print minimum_tier.

The CLI is a thin projection: each ``Surface.CLI`` capability becomes a typer
command, and the three scaffolder commands (``init``/``up``/``onboard``) are always
present. A rollup-returning command always prints ``minimum_tier`` (H7) and the
distribution; a command requires ``--tenant``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

from typer.testing import CliRunner
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.capabilities import Surface
from valuemaxx.cli.main import build_app

if TYPE_CHECKING:
    from pathlib import Path

    import typer

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


def test_up_command_runs() -> None:
    """`valuemaxx up` reports the embedded-SQLite default backend plan."""
    app = build_app()
    result = _runner.invoke(app, ["up"])
    assert result.exit_code == 0
    assert "sqlite" in result.stdout.lower()


def test_onboard_command_runs() -> None:
    """`valuemaxx onboard` invokes the onboarding flow (stub reports the steps)."""
    app = build_app()
    result = _runner.invoke(app, ["onboard"])
    assert result.exit_code == 0
    assert "onboard" in result.stdout.lower()
