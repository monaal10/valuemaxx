"""The ``valuemaxx`` CLI — a thin projection plus the three scaffolder commands.

``build_app`` assembles the typer app: it mounts every ``Surface.CLI`` capability as
a command (thin projection of the registry) and adds the three operator commands:

* ``valuemaxx init`` — the scaffolder stub: detect the host framework and report the
  SDK ``init()`` it would inject (the actual code-write is the onboarding agent's
  reviewable diff, never an unconfirmed auto-edit).
* ``valuemaxx up`` — run the backend with embedded SQLite by default.
* ``valuemaxx onboard`` — invoke the onboarding flow (scan -> propose -> validate).

Every capability command prints its rollup output with ``minimum_tier`` (H7) via
:mod:`valuemaxx.cli.render`; capability commands require ``--tenant``.
"""

from __future__ import annotations

from pathlib import Path

import typer
from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.cli.projection import mount_capabilities

# Frameworks the init scaffolder can detect, by a marker file in the target repo.
_FRAMEWORK_MARKERS: tuple[tuple[str, str], ...] = (
    ("fastapi", "main.py"),
    ("django", "manage.py"),
    ("express", "package.json"),
)

# Module-level typer Option singletons (typer evaluates these as defaults; defining
# them once avoids the B008 "call in argument default" pitfall).
_REPO_OPTION = typer.Option(Path(), "--repo", help="The target repository.")
_DB_OPTION = typer.Option("sqlite", "--db", help="Backend store (default: embedded SQLite).")


def _detect_framework(repo: Path) -> str:
    """Best-effort framework detection from marker files (stub heuristic)."""
    for framework, marker in _FRAMEWORK_MARKERS:
        if (repo / marker).exists():
            return framework
    return "unknown"


def init(repo: Path = _REPO_OPTION) -> None:
    """Scaffold the SDK init: detect the framework and report the injection plan.

    This is a stub: it detects the host framework and reports the
    ``valuemaxx.init()`` call it would inject. The actual edit is produced by the
    onboarding agent as a reviewable diff (a human confirms — never auto-applied).
    """
    framework = _detect_framework(repo)
    typer.echo(f"valuemaxx init: detected framework={framework}")
    typer.echo("plan: inject `valuemaxx.init()` at the app entrypoint (review the diff).")


def up(db: str = _DB_OPTION) -> None:
    """Run the backend with an embedded store (SQLite by default)."""
    typer.echo(f"valuemaxx up: starting backend with db={db} (embedded SQLite default).")


def onboard(repo: Path = _REPO_OPTION) -> None:
    """Invoke the onboarding flow: scan -> propose -> validate (reviewable diff)."""
    typer.echo(f"valuemaxx onboard: scanning {repo} -> propose -> validate.")
    typer.echo("onboard: candidate outcome rules are UNCONFIRMED until you review the diff.")


def build_app() -> typer.Typer:
    """Build the ``valuemaxx`` typer app: capability commands + init/up/onboard."""
    app = typer.Typer(
        name="valuemaxx",
        help="valuemaxx — AI margin intelligence: cost-per-outcome with confidence.",
        no_args_is_help=True,
        add_completion=False,
    )
    app.command(name="init")(init)
    app.command(name="up")(up)
    app.command(name="onboard")(onboard)
    mount_capabilities(app, build_default_registry())
    return app


app = build_app()


def main() -> None:
    """Console-script entry point for the ``valuemaxx`` CLI."""
    app()


__all__ = ["app", "build_app", "init", "main", "onboard", "up"]
